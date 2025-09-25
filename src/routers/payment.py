import os
from datetime import datetime, timedelta

import stripe
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from pydantic import UUID4, BaseModel
from requests import Session
from sqlalchemy import case, func

from src.api import schemas
from src.api.schemas import PaymentRequest
from src.common.email_service import send_email
from src.common.translate import translate_fields
from src.configs import database
from src.configs.config import EnvVar, logger
from src.models import models
from src.authentication.encryption import decrypt_password, secret_key

get_db = database.get_db
STRIPE_WEBHOOK_SECRET = os.getenv(EnvVar.StripeWebhookSecret.value)
STRIPE_API_KEY = os.getenv(EnvVar.StripeAPIKey.value)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter(prefix="/payment", tags=["Payment"])
stripe.api_key = STRIPE_API_KEY


class CheckoutSessionRequest(BaseModel):
    current_user: UUID4
    stripe_customer_id: str
    price_id: str
    subscriptionId: int
    duration: str
    successurl: str = None
    cancelurl: str = None


class PaymentRequest(BaseModel):
    current_user: UUID4
    price_id: str
    stripe_customer_id: str
    duration: str


class CancelRequest(BaseModel):
    current_user: UUID4
    stripe_subscription_id: str

def check_bool(value):
    if value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False
    else:
        raise ValueError("Invalid boolean value")

# For titanium subscriptions
@router.post("/create-titanium-checkout-session")
async def create_titanium_checkout_session(
    data: schemas.TitaniumResponse, db: Session = Depends(get_db)
):
    try:
        # Create the Stripe Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": "Custom Titanium Subscription",
                            "description": "Custom Titanium Subscription",
                        },
                        "unit_amount": int(data.price * 100),
                    },
                    "quantity": 1,
                }
            ],
            success_url=data.successurl,
            cancel_url=data.cancelurl,
            metadata={
                "service_provider_id": data.providerId,
                "clients_count": data.clients_count,
                "duration": data.duration,
                "price": data.price,
                "chatRestrictions": data.chat_restrictions,
                "communications": data.communications,
                "risk_reward_clients": data.risk_reward_clients,
                "risk_reward_prospective_clients": data.risk_reward_prospective_clients,
                "risk_reward_provider": data.risk_reward_provider,
                "sub_type": "custom",
            },
        )
        user_obj = (
            db.query(models.User).filter(models.User.uuid == data.providerId).first()
        )
        body = templates.get_template("paymentLink.html").render(
            service_provider_name=user_obj.details["service_provider"]["name"],
            payment_link=session.url,
            support_contact="888-888-888",
        )
        await send_email(
            user_obj.useremail,
            "Complete Your Titanium Plan Enrollment – Payment Link Inside",
            body,
        )
        return {"status": status.HTTP_200_OK, "message": "Email sended successfully"}
    except stripe.error.CardError as e:
        # Handle card errors
        raise HTTPException(status_code=400, detail=str(e))
    except stripe.error.RateLimitError as e:
        # Handle rate limit errors
        raise HTTPException(status_code=429, detail=str(e))
    except stripe.error.AuthenticationError as e:
        # Handle authentication errors
        raise HTTPException(status_code=401, detail=str(e))
    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=str(e))


# For normal subscriptions
@router.post("/api/create-checkout-session")
async def create_checkout_session(
    data: CheckoutSessionRequest, db: Session = Depends(get_db)
):
    membership = (
        db.query(models.Membership)
        .filter(models.Membership.uuid == data.current_user)
        .order_by(models.Membership.expiry_date.desc())
        .first()
    )
    subscription_data = {}
    if membership is None:
        is_trial = True
        # subscription_data["trial_end"] = two_minutes_from_now
        subscription_data["trial_period_days"] = 90

    else:
        is_trial = False
    try:
        # Create the Stripe Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription", 
            line_items=[
                {
                    "price": data.price_id,
                    "quantity": 1,
                },
            ],
            success_url=data.successurl,
            cancel_url=data.cancelurl,
            metadata={
                "service_provider_id": data.current_user,
                "is_trial": is_trial,
                "subscription_id": data.subscriptionId,
                "duration": data.duration,
                "price": 0,
            },
            subscription_data=subscription_data,
        )
        return {"id": session.id, "url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upgrade-subscription")
async def upgrade_subscription(data: PaymentRequest, db: Session = Depends(get_db)):
    memberships = (
        db.query(models.Membership)
        .filter(
            (models.Membership.uuid == data.current_user)
            & (models.Membership.status.in_(["active", "trial", "upcoming"]))
        )
        .order_by(models.Membership.expiry_date.desc())
        .all()
    )

    if len(memberships) == 2:
        status = {membership.status for membership in memberships}
        if "upcoming" in status and ("active" in status or "trial" in status):
            return {"status": "error", "message": "You already have one upcoming plan"}
    membership = memberships[0]

    subscription = stripe.Subscription.retrieve(membership.stripe_subscription_id)
    price_obj = stripe.Price.retrieve(data.price_id)
    amount = price_obj["unit_amount"] / 100
    end_date = datetime.fromtimestamp(subscription["current_period_end"])
    subscription_obj = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.price_details[data.duration]["stripe_price_id"].astext
            == data.price_id
        )
        .first()
    )
    try:
        schedule = stripe.SubscriptionSchedule.create(
            customer=data.stripe_customer_id,
            start_date=end_date,
            end_behavior="release",
            phases=[
                {
                    "items": [
                        {
                            "price": data.price_id,
                            "quantity": 1,
                        },
                    ],
                    "iterations": 1,
                },
            ],
            metadata={
                "service_provider_id": data.current_user,
                "is_trial": "False",
                "duration": data.duration,
                "price": amount,
                "subscription_id": subscription_obj.subscription_id,
            },
        )
        return {"status": "success", "message": "Subscription upgraded successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/cancel-subscription")
async def cancel_subscription(data: CancelRequest, db: Session = Depends(get_db)):
    try:
        membership = db.query(models.Membership).filter(
            models.Membership.stripe_subscription_id == data.stripe_subscription_id
        )

        if not membership.first():
            return {"status": "error", "message": "No subscription found"}
        membership = membership.first()
        if membership.status == "trial" or membership.status == "active":
            stripe.Subscription.modify(
                data.stripe_subscription_id, cancel_at_period_end=True
            )
        elif membership.status == "upcoming":
            stripe.SubscriptionSchedule.cancel(data.stripe_subscription_id)
        return {"status": "success", "message": "Subscription cancelled successfully"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    endpoint_secret = STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        # Invalid payload
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        if metadata.get("duration") == "monthly":
            expiry_date = datetime.fromtimestamp(session["created"]) + relativedelta(
                months=1
            )
        elif metadata.get("duration") == "quarterly":
            expiry_date = datetime.fromtimestamp(session["created"]) + relativedelta(
                months=3
            )
        elif metadata.get("duration") == "yearly":
            expiry_date = datetime.fromtimestamp(session["created"]) + relativedelta(
                years=1
            )

        if metadata.get("sub_type") == "custom":
            user_obj = db.query(models.User).filter(models.User.uuid == metadata.get("service_provider_id")).first()
            if user_obj:
                user_obj.is_titanium_requested = False
                db.commit()
                db.refresh(user_obj)
            new_titanium_membership = models.Titanium(
                uuid=metadata.get("service_provider_id"),
                clients_count=metadata.get("clients_count"),
                chat_restriction=check_bool(metadata.get("chatRestrictions")),
                view_other_client=metadata.get("communications"),
                risk_reward_clients=check_bool(metadata.get("risk_reward_clients")),
                risk_reward_prospective_clients=check_bool(
                    metadata.get("risk_reward_prospective_clients")
                ),
                risk_reward_provider=check_bool(metadata.get("risk_reward_provider")),
                start_date=datetime.fromtimestamp(session["created"]),
                expiry_date=expiry_date,
                created_at=datetime.fromtimestamp(session["created"]),
                updated_at=datetime.fromtimestamp(session["created"]),
                duration=metadata.get("duration"),
                status="active",
                payment_status="succeeded",
                payment_price=int(float(metadata.get("price"))),
            )
            db.add(new_titanium_membership)
            db.commit()
            db.refresh(new_titanium_membership)
            logger.log_info(f"New titanium membership created {new_titanium_membership}")
            user_obj = (
                db.query(models.User)
                .filter(models.User.uuid == metadata.get("service_provider_id"))
                .first()
            )
            password = decrypt_password(user_obj.password, secret_key)
            body = templates.get_template("titaniumCreated.html").render(
                service_provider_name=user_obj.details["service_provider"]["name"],
                login_url="https://hopeforeverybody.org",
                email=user_obj.useremail,
                temp_password=password,
                support_contact="888-888-8888",
            )
            await send_email(
                user_obj.useremail,
                "Welcome to the Titanium Plan – Your Access Details Inside",
                body,
            )
            logger.log_info("Email sended to user successfully")
        else:
            billing_date = datetime.fromtimestamp(session["created"])

            duration_map = {
                "monthly": relativedelta(months=1),
                "quarterly": relativedelta(months=3),
                "yearly": relativedelta(years=1),
            }

            duration = metadata.get("duration")

            # Create new membership
            new_membership = models.Membership(
                uuid=metadata.get("service_provider_id"),
                subscription_id=metadata.get("subscription_id"),
                payment_price=int(float(metadata.get("price"))),
                billing_date=billing_date,
                duration=duration,
                start_date=billing_date,
                stripe_subscription_id=session.get("subscription"),
                payment_status="succeeded",
            )
            if metadata.get("is_trial") == "True":
                user_obj = (
                    db.query(models.User)
                    .filter(models.User.uuid == metadata.get("service_provider_id"))
                    .first()
                )
                subscription_obj = (
                    db.query(models.Subscription)
                    .filter(
                        models.Subscription.subscription_id
                        == metadata.get("subscription_id")
                    )
                    .first()
                )
                user_email = user_obj.useremail
                password = decrypt_password(user_obj.password, secret_key)
                body = templates.get_template("trialWelcome.html").render(
                    service_provider_name=user_obj.details["service_provider"]["name"],
                    plan_name=subscription_obj.name,
                    login_url="https://hopeforeverybody.org",
                    email=user_obj.useremail,
                    temp_password=password,
                )
                await send_email(
                    user_email,
                    "Welcome to the Trial Plan – Your Access Details Inside",
                    body,
                )
                logger.log_info("Email sended to user successfully")
                # Set trial period
                new_membership.status = "trial"
                new_membership.expiry_date = billing_date + relativedelta(days=90)
                new_membership.trial_start_date = billing_date
                new_membership.trial_end_date = billing_date + relativedelta(days=90)
            else:
                new_membership.status = "active"
                new_membership.expiry_date = billing_date + duration_map[duration]
                new_membership.trial_start_date = None
                new_membership.trial_end_date = None

            db.add(new_membership)
            db.commit()
            db.refresh(new_membership)
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        subscription_id = subscription.get("id")
        status = subscription.get("status")

        membership = (
            db.query(models.Membership).filter(
                models.Membership.stripe_subscription_id == subscription_id
            )
        ).first()
        if membership is not None and status == "active":
            membership.status = status
            membership.start_date = datetime.fromtimestamp(
                subscription["current_period_start"]
            )
            membership.billing_date = datetime.fromtimestamp(
                subscription["current_period_start"]
            )
            membership.expiry_date = datetime.fromtimestamp(
                subscription["current_period_end"]
            )
            membership.payment_status = "succeeded"
            db.commit()
            db.refresh(membership)
    elif event["type"] == "customer.subscription.trials_will_end":
        # send an email to the user
        customer_id = event["data"]["object"]["customer"]

        user_obj = (
            db.query(models.User)
            .filter(models.User.stripe_customer_id == customer_id)
            .first()
        )

        # get the email id of that user :
        email_id = user_obj.useremail
        # get the name of that user :
        name = user_obj.details["service_provider"]["name"].astext
        # get the subscription id of that user :

    # -----------------
    elif event["type"] == "customer.subscription.created":
        subscription = event["data"]["object"]
        schedule_id = subscription.get("schedule")
        subscription_id = subscription.get("id")
        # Changing the status of membership to active when upgrade/downgrade is done
        if schedule_id is not None:
            membership = (
                db.query(models.Membership).filter(
                    models.Membership.stripe_subscription_id == schedule_id
                )
            ).first()

            if membership:
                membership.status = "active"
                membership.strip_subscription_id = subscription_id
                membership.payment_status = "succeeded"
                db.commit()
                db.refresh(membership)
    elif event["type"] == "subscription_schedule.created":
        schdule = event["data"]["object"]
        metaData = schdule.get("metadata", {})
        membership = (
            db.query(models.Membership)
            .filter(
                (models.Membership.status.in_(["active", "trial"]))
                & (models.Membership.uuid == metaData.get("service_provider_id"))
            )
            .first()
        )
        if membership:
            stripe.Subscription.modify(
                membership.stripe_subscription_id, cancel_at_period_end=True
            )
        new_membership = models.Membership(
            uuid=metaData.get("service_provider_id"),
            subscription_id=metaData.get("subscription_id"),
            payment_price=int(float(metaData.get("price"))),
            duration=metaData.get("duration"),
            status="upcoming",
            payment_status="pending",
            start_date=datetime.fromtimestamp(schdule["phases"][0]["start_date"]),
            billing_date=datetime.fromtimestamp(schdule["phases"][0]["start_date"]),
            expiry_date=datetime.fromtimestamp(schdule["phases"][0]["end_date"]),
            stripe_subscription_id=schdule["id"],
            trial_start_date=None,
            trial_end_date=None,
        )
        db.add(new_membership)
        db.commit()

    elif event["type"] == "subscription_schedule.canceled":
        schedule = event["data"]["object"]
        subscription_id = schedule.get("id")
        membership = (
            db.query(models.Membership)
            .filter(models.Membership.stripe_subscription_id == subscription_id)
            .first()
        )
        if membership:
            membership.status = "cancelled"
            db.commit()
            db.refresh(membership)

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        subscription_id = subscription.get("id")
        membership = (
            db.query(models.Membership)
            .filter(models.Membership.stripe_subscription_id == subscription_id)
            .first()
        )
        if membership:
            membership.status = "cancelled"
            db.commit()
            db.refresh(membership)
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(router, host="0.0.0.0", port=8100)


@router.get("/revenue")
async def get_revenue(
    skip: int = 0,
    limit: int = 10,
    search: str = None,
    name: str = None,
    signup_date: str = None,
    latest_billing_date: str = None,
    expiry_date: str = None,
    useremail: str = None,
    sort_by: str = None,
    sort_order: str = "asc",
    old_new: str = None,
    db: Session = Depends(get_db),
):
    name_translate = await translate_fields(name, fields=[])
    search_translate = await translate_fields(search, fields=[])
    useremail_translate = await translate_fields(useremail, fields=[])

    # Subquery to get the latest membership for each provider using ROW_NUMBER.
    latest_subquery = db.query(
        models.Membership.uuid.label("sp_uuid"),
        models.Membership.billing_date,
        models.Membership.expiry_date,
        models.Membership.subscription_id,
        func.row_number()
        .over(
            partition_by=models.Membership.uuid,
            order_by=models.Membership.billing_date.desc(),
        )
        .label("row_num"),
    ).subquery()

    # Subquery to calculate the total amount paid (sum of all subscription prices) for each provider.
    total_amount_subquery = (
        db.query(
            models.Membership.uuid.label("sp_uuid"),
            func.sum(models.Membership.payment_price).label("total_amount_paid"),
        )
        .join(
            models.Subscription,
            models.Membership.subscription_id == models.Subscription.subscription_id,
        )
        .group_by(models.Membership.uuid)
        .subquery()
    )

    # Main query: join only the latest membership record (row_num == 1) and its related subscription.
    query = (
        db.query(
            models.User.uuid,
            models.User.useremail,
            models.User.details["service_provider"]["name"].astext.label(
                "provider_name"
            ),
            models.User.created_at.label("sign_up_date"),
            latest_subquery.c.billing_date.label("latest_billing_date"),
            latest_subquery.c.expiry_date.label("expiry_date"),
            models.Subscription.name.label("subscription_name"),
            total_amount_subquery.c.total_amount_paid.label("total_amount"),
            # Based on the latest subscription's duration, only one of these will be nonzero.
            case(
                (
                    func.lower(models.Membership.duration) == "month",
                    models.Membership.payment_price,
                ),
                else_=0,
            ).label("monthly_amount"),
            case(
                (
                    func.lower(models.Membership.duration) == "quarter",
                    models.Membership.payment_price,
                ),
                else_=0,
            ).label("quarterly_amount"),
            case(
                (
                    func.lower(models.Membership.duration) == "year",
                    models.Membership.payment_price,
                ),
                else_=0,
            ).label("yearly_amount"),
        )
        # Join the latest membership subquery (limiting to the latest record per provider).
        .join(
            latest_subquery,
            (models.User.uuid == latest_subquery.c.sp_uuid)
            & (latest_subquery.c.row_num == 1),
        )
        # Join the subscription details for that latest membership.
        .join(
            models.Subscription,
            latest_subquery.c.subscription_id == models.Subscription.subscription_id,
        )
        # Join the total amount subquery to get the aggregated total.
        .join(
            total_amount_subquery, models.User.uuid == total_amount_subquery.c.sp_uuid
        )
        .filter(
            models.User.role_type == "service_provider", models.User.is_deleted == False
        )
        .distinct()
    )

    # Apply additional filters.
    if search_translate:
        query = query.filter(
            models.User.details["service_provider"]["name"].astext.ilike(
                f"%{search_translate}%"
            )
            | models.Subscription.name.ilike(f"%{search}%")
        )

    if name_translate:
        query = query.filter(models.Subscription.name.ilike(f"%{name_translate}%"))

    if signup_date:
        try:
            signup_date_obj = datetime.strptime(signup_date, "%Y-%m-%d").date()
            # Adjust field as needed if your model uses a different signup date field.
            query = query.filter(func.date(models.User.created_at) == signup_date_obj)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
            )

    if latest_billing_date:
        try:
            billing_date_obj = datetime.strptime(latest_billing_date, "%Y-%m-%d").date()
            query = query.filter(
                func.date(latest_subquery.c.billing_date) == billing_date_obj
            )
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
            )

    if expiry_date:
        try:
            expiry_date_obj = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            query = query.filter(
                func.date(latest_subquery.c.expiry_date) == expiry_date_obj
            )
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
            )

    if useremail_translate:
        query = query.filter(models.User.useremail.ilike(f"%{useremail_translate}%"))

    if old_new:
        filter_date = datetime.now() - timedelta(days=30)
        if old_new.lower() == "new":
            query = query.filter(models.User.created_at >= filter_date)
        elif old_new.lower() == "old":
            query = query.filter(models.User.created_at < filter_date)
        else:
            raise HTTPException(
                status_code=400, detail="Invalid value for old_new. Use 'new' or 'old'."
            )

    if sort_by:
        if sort_by in ["name", "email", "created_at", "status"]:
            column = {
                "name": models.User.details["service_provider"]["name"].astext,
                "email": models.User.useremail,
                "created_at": models.User.created_at,
                "status": models.User.status,
            }.get(sort_by)

            if sort_order.lower() == "desc":
                query = query.order_by(column.desc())
            else:
                query = query.order_by(column.asc())

    # Apply pagination.
    total_count_query = db.query(func.count()).select_from(query.subquery()).scalar()
    query = query.limit(limit).offset(skip)
    results = query.all()
    main_subq = query.subquery()
    total_revenue = db.query(
        func.coalesce(func.sum(main_subq.c.total_amount), 0)
    ).scalar()

    # Format the response.
    revenue_data = [
        {
            "uuid": row.uuid,
            "provider_name": row.provider_name or "Unknown",
            "provider_email": row.useremail,
            "sign_up_date": row.sign_up_date.strftime("%Y-%m-%d"),
            "latest_billing_date": row.latest_billing_date.strftime("%Y-%m-%d")
            if row.latest_billing_date
            else None,
            "expiry_date": row.expiry_date.strftime("%Y-%m-%d")
            if row.expiry_date
            else None,
            "subscription_plan": row.subscription_name,
            "total_amount_paid": row.total_amount,
            "monthly_amount": row.monthly_amount,
            "quarterly_amount": row.quarterly_amount,
            "yearly_amount": row.yearly_amount,
        }
        for row in results
    ]

    return {
        "total_count": total_count_query,
        "total_revenue": total_revenue,
        "data": revenue_data,
    }
