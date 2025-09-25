import csv
import io
import json
import os
import uuid
from datetime import datetime

import stripe
from fastapi import Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import UUID4, EmailStr
from sqlalchemy import UUID, String, case, cast, func, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy import update
from src.api import schemas
from src.api.schemas import SubAdminCreate
from src.authentication.encryption import decrypt_password, encrypt_password, secret_key
from src.common.email_service import send_email
from src.common.translate import translate_fields
from src.configs import database
from src.configs.config import logger
from src.models import models
from src.routers.chat import manager
from dotenv import load_dotenv
load_dotenv()

get_db = database.get_db

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AVATAR_DIR = os.path.join(BASE_DIR, "avatars")


def get_avatars():
    try:
        avatars = [
            f"/avatars/{file}"
            for file in os.listdir(AVATAR_DIR)
            if os.path.isfile(os.path.join(AVATAR_DIR, file))
        ]
        return {"avatars": avatars}
    except Exception as e:
        return {"error": str(e)}


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMAGE_DIR = os.path.join(BASE_DIR, "hfe_images")
AVATAR_DIR = os.path.join(BASE_DIR, "avatars")
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)


def save_uploaded_file(
    file: UploadFile, request: Request, folder: str | None = "hfe_images"
) -> str | None:
    """Save uploaded file and return its full server URL."""
    if not file:
        return None

    os.makedirs(folder, exist_ok=True)

    file_uuid = str(uuid.uuid4())
    _, ext = os.path.splitext(file.filename)
    sanitized_filename = file.filename.replace(" ", "_")
    new_filename = f"{file_uuid}_{sanitized_filename}"
    file_path = os.path.join(folder, new_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        base_url = str(request.base_url).rstrip("/")
        return f"{base_url}/api/images/{new_filename}"

    except Exception as e:
        logger.log_error(f"Error saving file: {e}")
        return None


async def create_sub_admin(
    request: Request,
    sub_admin_original: SubAdminCreate,
    profile_img: UploadFile = File(None),
    header_image: UploadFile = File(None),
    avatar_selection: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        sub_admin = await translate_fields(
            sub_admin_original,
            fields=["first_name", "last_name", "gender", "description"],
        )

        logger.log_info(f"Received payload: {sub_admin.dict()}")
        encrypted_password = encrypt_password(sub_admin.password, secret_key)

        if profile_img:
            logger.log_info(
                f"Received profile picture: {profile_img.filename}, Content-Type: {profile_img.content_type}"
            )
        else:
            logger.log_info("No profile picture received.")

        if header_image:
            logger.log_info(
                f"Received header image: {header_image.filename}, Content-Type: {header_image.content_type}"
            )
        else:
            logger.log_info("No header image received.")

        existing_subadmin = (
            db.query(models.User)
            .filter(models.User.useremail == sub_admin.useremail)
            .first()
        )
        if existing_subadmin:
            if not existing_subadmin.is_deleted:
                logger.log_warning(
                    f"Sub-admin with email {sub_admin.useremail} already exists."
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Sub Admin with {sub_admin.useremail} already exists and is active.",
                )
            logger.log_info(
                f"Sub-admin {sub_admin.useremail} exists but was marked as deleted. Reusing the email."
            )

        profile_img_url = (
            save_uploaded_file(profile_img, request) if profile_img else None
        )
        header_img_url = (
            save_uploaded_file(header_image, request) if header_image else None
        )
        logger.log_info(f"Processed profile image URL: {profile_img_url}")
        logger.log_info(f"Processed header image URL: {header_img_url}")

        # Handle avatar selection
        if avatar_selection:
            avatar_list = [
                f"/avatars/{img}"
                for img in os.listdir(AVATAR_DIR)
                if img.endswith(".svg")
            ]
            if avatar_selection in avatar_list:
                profile_img_url = (
                    f"{str(request.base_url).rstrip('/')}{avatar_selection}"
                )
        if not profile_img_url:
            profile_img_url = None

        # Generate a new UUID
        new_uuid = uuid.uuid4()
        logger.log_info(f"Generated UUID for new sub-admin: {new_uuid}")

        # Creating sub-admin entry
        new_sub_admin = models.User(
            uuid=new_uuid,
            created_by=sub_admin.uuid,
            useremail=sub_admin.useremail,
            password=encrypted_password,
            role_type="sub_admin",
            profile_img=profile_img_url,
            header_img=header_img_url,
            is_activated=True,
            status="verified",
            details={
                "sub_admin": {
                    "first_name": sub_admin.first_name,
                    "last_name": sub_admin.last_name,
                    "gender": sub_admin.gender or "Male",
                    "phone": sub_admin.phone,
                    "email": sub_admin.useremail,
                }
            },
            permission=sub_admin.permission,
        )
        db.add(new_sub_admin)
        db.commit()
        db.refresh(new_sub_admin)
        logger.log_info(f"Sub-admin {sub_admin.useremail} created successfully.")

        # Sending welcome email
        subject = "Welcome to the Platform!"
        body = """
        
        """
        body = f"""
        <html>
            <body>
                <h1>Welcome, {sub_admin.first_name} {sub_admin.last_name}!</h1>
                <p>You have been added as a subadmin on our platform.</p>
                <p>Your login credentials are:</p>
                <ul>
                    <li><strong>Email:</strong> {sub_admin.useremail}</li>
                    <li><strong>Password:</strong> {sub_admin.password}</li>
                </ul>
                <p>Please log in and change your password immediately.</p>
                <p>Regards,</p>
                <p>The Admin Team</p>
            </body>
        </html>
        """
        await send_email(sub_admin.useremail, subject, body)
        logger.log_info(f"Welcome email sent to {sub_admin.useremail}")

        return {
            "uuid": new_sub_admin.uuid,
            "first_name": sub_admin.first_name,
            "last_name": sub_admin.last_name,
            "phone": sub_admin.phone,
            "gender": sub_admin.gender or "Male",
            "useremail": sub_admin.useremail,
            "profile_img": profile_img_url,
            "permission": sub_admin.permission,
            "created_by": sub_admin.uuid,
        }

    except HTTPException as e:
        logger.log_error(f"HTTP Exception: {e.detail}")
        raise e

    except Exception:
        # logger.log_error("An unexpected error occurred while creating the sub-admin.")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def update_subadmin(
    uuid: UUID,
    request: Request,
    useremail: EmailStr,
    update_original: schemas.editSubAdmin,
    profile_img: UploadFile | None = None,
    header_image: UploadFile | None = None,
    avatar_selection: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        update = await translate_fields(
            update_original, fields=["first_name", "last_name", "gender", "description",'email', 'phone']
        )

        logger.log_info(f"Received payload: {update.model_dump()}")

        sub_admin = db.query(models.User).filter(models.User.uuid == uuid).first()
        if not sub_admin:
            raise HTTPException(status_code=404, detail="SubAdmin not found")

        updated_provider = update.model_dump(exclude_unset=True)
        update_data = {}

        # Preserve existing values
        profile_img_url = sub_admin.profile_img
        header_img_url = sub_admin.header_img

        # Get available avatars
        avatar_list = [
            f"/avatars/{img}" for img in os.listdir(AVATAR_DIR) if img.endswith(".svg")
        ]

        changes_detected = False

        # User chooses an avatar after already having a profile image
        if avatar_selection:
            if avatar_selection in avatar_list:
                new_avatar_url = (
                    f"{str(request.base_url).rstrip('/')}{avatar_selection}"
                )
                if profile_img_url != new_avatar_url:  # Only update if it's different
                    profile_img_url = new_avatar_url
                    update_data["profile_img"] = profile_img_url
                    changes_detected = True
                    logger.log_info(
                        f"Profile image replaced with avatar: {profile_img_url}"
                    )
            else:
                raise HTTPException(status_code=400, detail="Invalid avatar selection")

        # User uploads a new profile image (profile image takes priority over avatar)
        if profile_img:
            new_profile_img_url = save_uploaded_file(profile_img, request)
            if profile_img_url != new_profile_img_url:  # Only update if it's different
                profile_img_url = new_profile_img_url
                update_data["profile_img"] = profile_img_url
                changes_detected = True
                logger.log_info(f"New profile image uploaded: {profile_img_url}")

        # Handle header image update
        if header_image:
            new_header_img_url = save_uploaded_file(header_image, request)
            if header_img_url != new_header_img_url:  # Only update if it's different
                header_img_url = new_header_img_url
                update_data["header_img"] = header_img_url
                changes_detected = True
                logger.log_info(f"Header image updated: {header_img_url}")

        if useremail:
            update_data['useremail'] = useremail
            changes_detected = True
        # Handle permission update (only update if changed)
        if update.permission and update.permission != sub_admin.permission:
            try:
                json.dumps(update.permission)  # Validate JSON format
                db.query(models.User).filter(models.User.uuid == uuid).update(
                    {"permission": func.cast(update.permission, JSONB)}
                )
                changes_detected = True
                logger.log_info("Permissions updated")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid JSON format for permission field"
                )

        # Track detail changes dynamically
        details_updates = {}
        for key, value in updated_provider.items():
            if key in sub_admin.details.get("sub_admin", {}) and value is not None:
                if (
                    sub_admin.details["sub_admin"].get(key) != value
                ):  # Only update if different
                    details_updates[key] = value
                    changes_detected = True

        # Apply detail updates in the database
        if details_updates:
            for key, value in details_updates.items():
                db.query(models.User).filter(models.User.uuid == uuid).update(
                    {
                        "details": func.jsonb_set(
                            models.User.details, f"{{sub_admin,{key}}}", f'"{value}"'
                        )
                    }
                )

        # Apply updates to main User fields
        if update_data:
            db.query(models.User).filter(models.User.uuid == uuid).update(update_data)

        if changes_detected:
            db.commit()
            db.refresh(sub_admin)
            logger.log_info(f"Updated fields: {update_data} and {details_updates}")
            return {"message": "SubAdmin updated successfully", "sub_admin": sub_admin}

        return {"message": "No changes detected", "sub_admin": sub_admin}

    except Exception as e:
        logger.log_error(f"Error updating subadmin: {e!s}")
        raise HTTPException(status_code=500, detail=str(e))


async def sub_admin_status(sub_admin_uuid: str, db: Session):
    try:
        sub_admin_uuid = uuid.UUID(sub_admin_uuid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    try:
        del_subadmin = (
            db.query(models.User).filter(models.User.uuid == sub_admin_uuid).first()
        )

        if del_subadmin is None:
            raise HTTPException(status_code=404, detail="Sub Admin not found")
        del_subadmin.is_activated = not del_subadmin.is_activated
        db.commit()
        status = "activated" if del_subadmin.is_activated else "deactivated"
        return {
            "detail": "Sub Admin status toggled successfully",
            "is_activated": del_subadmin.is_activated,
        }

    except HTTPException as e:
        raise e


def soft_delete_subadmin(
    subadmin_uuid: uuid.UUID,
    request: schemas.SoftDeleteRequest,
    db: Session = Depends(get_db),
):
    subadmin = (
        db.query(models.User)
        .filter(models.User.uuid == subadmin_uuid, models.User.role_type == "sub_admin")
        .first()
    )
    if not subadmin:
        raise HTTPException(status_code=404, detail="SubAdmin not found")

    subadmin.is_deleted = True
    subadmin.deleted_by = request.deleted_by
    subadmin.deleted_at = datetime.now()

    db.commit()
    db.refresh(subadmin)

    return {"detail": "User account deleted."}


def get_sub_admin(subadmin_uuid: uuid, db: Session):
    try:
        subadmin = (
            db.query(models.User).filter(models.User.uuid == subadmin_uuid).first()
        )
        if not subadmin:
            return JSONResponse(status_code=404, content="Sub Admin not found")
        decrypted_password = decrypt_password(subadmin.password, secret_key)
        profile_img_path = subadmin.profile_img if subadmin.profile_img else None
        header_img_path = subadmin.header_img if subadmin.header_img else None
        return {
            "uuid": subadmin.uuid,
            "first_name": subadmin.details.get("sub_admin", {}).get("first_name", ""),
            "last_name": subadmin.details.get("sub_admin", {}).get("last_name", ""),
            "phone": subadmin.details.get("sub_admin", {}).get("phone", ""),
            "useremail": subadmin.useremail,
            "gender": subadmin.details.get("sub_admin", {}).get("gender", ""),
            "permission": subadmin.permission,
            "profile_img": profile_img_path,
            "created_by": subadmin.created_by,
            "is_activated": subadmin.is_activated,
            "header_img": header_img_path,
            # "password": decrypted_password,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


async def get_all_subadmins(
    skip: int, limit: int, db: Session, name_original: str = None
):
    try:
        name = await translate_fields(name_original, fields=[])

        query = (
            db.query(models.User)
            .filter(
                models.User.role_type == "sub_admin", models.User.is_deleted == False
            )
            .order_by(models.User.created_at.desc())
        )

        if name:
            query = query.filter(
                (
                    models.User.details["sub_admin"]["first_name"].astext.ilike(
                        f"%{name}%"
                    )
                    | models.User.details["sub_admin"]["last_name"].astext.ilike(
                        f"%{name}%"
                    )
                    | models.User.details["sub_admin"]["email"].astext.ilike(
                        f"%{name}%"
                    )
                )
                | models.User.details["sub_admin"]["phone"].astext.ilike(f"%{name}%")
            )

        subadmins = query.offset(skip).limit(limit).all()
        total_subadmins = query.count()

        formatted_subadmins = [
            {
                "uuid": str(subadmin.uuid),
                "first_name": subadmin.details.get("sub_admin", {}).get(
                    "first_name", ""
                ),
                "last_name": subadmin.details.get("sub_admin", {}).get("last_name", ""),
                "phone": subadmin.details.get("sub_admin", {}).get("phone", ""),
                "useremail": subadmin.useremail,
                "profile_img": subadmin.profile_img if subadmin.profile_img else None,
                "is_activated": subadmin.is_activated,
                "created_by": subadmin.created_by,
                "created_at": subadmin.created_at,
                "updated_at": subadmin.updated_at,
                "is_deleted": subadmin.is_deleted,
                "updated_by": subadmin.updated_by,
                "deleted_by": subadmin.deleted_by,
                "deleted_at": subadmin.deleted_at,
                "header_img": subadmin.header_img if subadmin.header_img else None,
                "password": subadmin.password,
                "role_type": subadmin.role_type,
                "permission": subadmin.permission,
                "gender": subadmin.details.get("sub_admin", {}).get("gender", ""),
                "status": subadmin.status,
            }
            for subadmin in subadmins
        ]

        return {"total_subadmins": total_subadmins, "subadmins": formatted_subadmins}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e!s}",
        )


stripe.api_key = os.environ.get("STRIPE_API_KEY")


def create_subscriptions(subscription: schemas.createSubscription, db: Session):
    try:
        # Validate and check for existing subscription
        user = (
            db.query(models.User)
            .filter(models.User.uuid == subscription.created_by)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        existing_subscription = (
            db.query(models.Subscription)
            .filter(models.Subscription.name == subscription.name)
            .first()
        )
        if existing_subscription:
            raise HTTPException(status_code=409, detail="Subscription already exists")

        # Create a new subscription instance in your database
        new_subscription = models.Subscription(
            name=subscription.name,
            description=subscription.description,
            created_by=subscription.created_by,
            clients_count=subscription.clients_count,
            view_other_client=subscription.view_other_client,
            chat_with_prospective_clients=subscription.chat_with_prospective_clients,
            chat_restriction=subscription.chat_restriction,
            risk_reward_clients=subscription.risk_reward_clients,
            risk_reward_prospective_clients=subscription.risk_reward_prospective_clients,
            risk_reward_provider=subscription.risk_reward_provider,
            price_details={
                "monthly": {
                    "amount": subscription.price_details["monthly"].amount,
                    "discount": 0,
                    "stripe_price_id": "",
                },
                "quarterly": {
                    "amount": subscription.price_details["quarterly"].amount,
                    "discount": subscription.price_details["quarterly"].discount or 0,
                    "stripe_price_id": "",
                },
                "yearly": {
                    "amount": subscription.price_details["yearly"].amount,
                    "discount": subscription.price_details["yearly"].discount or 0,
                    "stripe_price_id": "",
                },
            },
        )
        # Create a product in Stripe for the subscription
        stripe_product = stripe.Product.create(
            name=new_subscription.name,
            type="service",
        )
        # Create a price on Stripe using the product
        for duration, price_detail in subscription.price_details.items():
            interval_mapping = {
                "monthly": ("month", 1),
                "quarterly": ("month", 3),
                "yearly": ("year", 1),
            }

            if duration not in interval_mapping:
                raise ValueError(
                    f"Invalid duration '{duration}'. Allowed values: {list(interval_mapping.keys())}"
                )

            interval, interval_count = interval_mapping[duration]

            stripe_price = stripe.Price.create(
                product=stripe_product.id,
                unit_amount=price_detail.amount * 100,  # Convert dollars to cents
                currency="usd",
                recurring={"interval": interval, "interval_count": interval_count},
            )
            new_subscription.price_details[f"{duration}"]["stripe_price_id"] = (
                stripe_price.id
            )
        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)

        return new_subscription

    except HTTPException as e:
        raise e


def update_subscription(
    subscription_id: int,
    updated_subscription: schemas.updateSubscription,
    db: Session = Depends(database.get_db),
):
    try:
        existing_subscription = (
            db.query(models.Subscription)
            .filter(models.Subscription.subscription_id == subscription_id)
            .first()
        )

        if not existing_subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found"
            )

        # Update fields dynamically based on provided values
        if updated_subscription.name is not None:
            existing_subscription.name = updated_subscription.name

        if updated_subscription.price_details is not None:
            updated_price_details = {}
            interval_mapping = {
                "monthly": ("month", 1),
                "quarterly": ("month", 3),
                "yearly": ("year", 1),
            }

            for key, price_detail in updated_subscription.price_details.items():
                # Validate duration
                if key not in interval_mapping:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid price duration '{key}'. Allowed: {list(interval_mapping.keys())}",
                    )

                # Archive the old price
                old_price_id = existing_subscription.price_details.get(key, {}).get(
                    "stripe_price_id"
                )
                if not old_price_id:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No old Stripe price ID provided for '{key}'",
                    )

                try:
                    old_price = stripe.Price.retrieve(old_price_id)
                    stripe_product_id = old_price.product
                    stripe.Price.modify(old_price_id, active=False)
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to archive old Stripe price {old_price_id}: {e!s}",
                    )

                # Create new Stripe price
                interval, interval_count = interval_mapping[key]
                try:
                    new_stripe_price = stripe.Price.create(
                        product=stripe_product_id,
                        unit_amount=price_detail.amount * 100,
                        currency="usd",
                        recurring={
                            "interval": interval,
                            "interval_count": interval_count,
                        },
                        metadata={"note": "Price updated via backend"},
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to create new Stripe price for '{key}': {e!s}",
                    )

                # Prepare updated price detail
                price_dict = price_detail.model_dump(exclude={"stripe_price_id"})
                price_dict["stripe_price_id"] = new_stripe_price.id
                updated_price_details[key] = price_dict

            existing_subscription.price_details = updated_price_details

        if updated_subscription.description is not None:
            existing_subscription.description = updated_subscription.description

        if updated_subscription.clients_count is not None:
            existing_subscription.clients_count = updated_subscription.clients_count

        if updated_subscription.view_other_client is not None:
            existing_subscription.view_other_client = (
                updated_subscription.view_other_client
            )

        if updated_subscription.chat_with_prospective_clients is not None:
            existing_subscription.chat_with_prospective_clients = (
                updated_subscription.chat_with_prospective_clients
            )

        if updated_subscription.chat_restriction is not None:
            existing_subscription.chat_restriction = (
                updated_subscription.chat_restriction
            )

        if updated_subscription.risk_reward_clients is not None:
            existing_subscription.risk_reward_clients = (
                updated_subscription.risk_reward_clients
            )

        if updated_subscription.risk_reward_prospective_clients is not None:
            existing_subscription.risk_reward_prospective_clients = (
                updated_subscription.risk_reward_prospective_clients
            )

        if updated_subscription.risk_reward_provider is not None:
            existing_subscription.risk_reward_provider = (
                updated_subscription.risk_reward_provider
            )

        if updated_subscription.updated_by is not None:
            existing_subscription.updated_by = updated_subscription.updated_by

        db.commit()
        db.refresh(existing_subscription)

        return existing_subscription

    except HTTPException as e:
        raise e


async def get_all_subscriptions(
    skip: int, limit: int, db: Session, name_original: str = None
):
    try:
        name = await translate_fields(name_original, fields=[])

        query = db.query(models.Subscription).order_by(models.Subscription.subscription_id.asc())

        if name:
            query = query.filter(models.Subscription.name.ilike(f"%{name}%"))

        subscriptions = query.offset(skip).limit(limit).all()
        total_subscriptions = query.count()

        return {
            "total_subscriptions": total_subscriptions,
            "all_subscriptions": subscriptions,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e!s}",
        )


def delete_subscriptions(subscription_id: int, db: Session):
    try:
        subscription = (
            db.query(models.Subscription)
            .filter(models.Subscription.subscription_id == subscription_id)
            .first()
        )
        if subscription is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Subscription is not found"
            )
        db.delete(subscription)
        db.commit()
        return {
            "detail": f"Subscription of id {subscription_id} is deleted successfully"
        }
    except HTTPException as e:
        raise e


async def create_cat(category_original: schemas.CategoryCreate, db: Session):
    try:
        category = await translate_fields(
            category_original, fields=["category_name", "sub_category_name"]
        )

        # Check if category already exists
        db_category = (
            db.query(models.Category)
            .filter(models.Category.category_name == category.category_name)
            .first()
        )
        if db_category:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Category already exist"
            )

        # Create new category
        new_category = models.Category(
            created_by=category.uuid,
            category_name=category.category_name,
            is_approved=True,
        )
        db.add(new_category)
        db.commit()
        db.refresh(new_category)

        # Create new subcategories
        for sub_category_name in category.sub_category_name:
            new_subcategory = models.SubCategory(
                created_by=category.uuid,
                category_id=new_category.category_id,
                sub_category_name=sub_category_name,
                is_approved=True
            )
            db.add(new_subcategory)
        db.commit()

        return {
            "category": new_category,
            "subcategories": db.query(models.SubCategory)
            .filter(models.SubCategory.category_id == new_category.category_id)
            .all(),
        }

    except HTTPException as e:
        raise e


async def create_sub(subcategory_original: schemas.SubCategoryCreate, db: Session):
    try:
        subcategory = await translate_fields(
            subcategory_original, fields=["sub_category_name"]
        )

        db_sub = (
            db.query(models.SubCategory)
            .filter(
                models.SubCategory.sub_category_name == subcategory.sub_category_name
            )
            .first()
        )
        if db_sub:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Subcatagory already exist"
            )
        new_sub = models.SubCategory(
            created_by=subcategory.uuid,
            category_id=subcategory.category_id,
            sub_category_name=subcategory.sub_category_name,
        )
        db.add(new_sub)
        db.commit()
        db.refresh(new_sub)
        return new_sub

    except HTTPException as e:
        raise e


def get_subcategories(category_id: int, db: Session):
    try:
        subcategories = (
            db.query(models.SubCategory)
            .filter(models.SubCategory.category_id == category_id)
            .all()
        )
        if not subcategories:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Subcategories not found"
            )
        subcategories.sort(key=lambda x: x.sub_category_name)
        return subcategories
    except HTTPException as e:
        raise e


async def get_all_categories(
    skip: int, limit: int, db: Session, name_original: str = None
):
    try:
        name = await translate_fields(name_original, fields=[])

        query = db.query(models.Category).outerjoin(models.Category.subcategories)

        # Apply name filter if provided
        if name:
            query = query.filter(
                models.Category.category_name.ilike(f"%{name}%")
                | (models.SubCategory.sub_category_name.ilike(f"%{name}%"))
            )

        query = query.distinct(models.Category.category_id) 
        total_categories = query.count()

        # Apply pagination
        categories = query.offset(skip).limit(limit).all()
        formatted_categories = []
        for category in categories:
            # Fetch subcategories separately
            subcategories = (
                db.query(models.SubCategory)
                .filter(models.SubCategory.category_id == category.category_id)
                .all()
            )

            formatted_subcategories = [
                {
                    "sub_category_id": subcategory.sub_category_id,
                    "sub_category_name": subcategory.sub_category_name,
                    "created_at": subcategory.created_at,
                    "updated_at": subcategory.updated_at,
                    "status": subcategory.is_approved,
                }
                for subcategory in subcategories
            ]

            formatted_categories.append(
                {
                    "category_id": category.category_id,
                    "category_name": category.category_name,
                    "created_at": category.created_at,
                    "updated_at": category.updated_at,
                    "status": category.is_approved,
                    "sub_category_name": formatted_subcategories,
                }
            )
        formatted_categories.sort(key=lambda x: x['category_name'].lower())
        return {
            "total_categories": total_categories,
            "categories": formatted_categories,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e!s}",
        )


def delete_category(category_id: int,user_uuid, db: Session):
    try:
        category = (
            db.query(models.Category)
            .filter(models.Category.category_id == category_id)
            .first()
        )
        if category is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Category is not found"
            )

        service_provider = db.query(models.User).filter(cast(models.User.details["service_provider"]["category_id"].astext,String,)== str(category_id)).count()
        if service_provider >= 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This category cannot be deleted because it is associated with one or more service providers.",
            )

        client = db.query(models.User).filter(or_(cast(models.User.details["client"]["primary_need"].astext, String)== str(category_id))).count()
        

        if client >=2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This category cannot be deleted because it is associated with one or more Client.",
            )

        db.delete(category)
        db.commit()
        
                
        user_obj = db.query(models.User).filter(models.User.uuid == user_uuid,models.User.is_deleted == False ).first()
        
        if user_obj:
            categories = user_obj.category_id.copy() if user_obj.category_id else {}
            updated = False
            for item in categories['category']:
                if item.get('id') == category_id:
                    item['status'] = "rejected"
                    for sub_cat_item in item['subCategory']:
                        sub_cat_item['status'] = "rejected"
                        updated = True
                    break
            if updated:
                user_obj.category_id = categories
                db.execute(update(models.User).where(models.User.uuid == user_uuid).values(category_id=categories))
                db.commit()
                db.refresh(user_obj)

        sub_categories = (
            db.query(models.SubCategory)
            .filter(models.SubCategory.category_id == category_id)
            .all()
        )
        for sub_category in sub_categories:
            db.delete(sub_category)
            db.commit()
        return {
            "detail": f"Category with ID {category_id} has been deleted, and all its subcategories have been removed."
        }
    except HTTPException as e:
        raise e


def delete_subcategory(sub_category_id: int, db: Session):
    try:
        subcategory = (
            db.query(models.SubCategory)
            .filter(models.SubCategory.sub_category_id == sub_category_id)
            .first()
        )
        if subcategory is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Sub Category is not found"
            )
        db.delete(subcategory)
        db.commit()
        return {
            "detail": f"Sub Category with ID {sub_category_id} is deleted successfully"
        }
    except HTTPException as e:
        raise e


async def edit_category(
    category_id: int, update_category_name, db: Session
):
    try:
        update_category = await translate_fields(
            update_category_name, fields=["category_name", "sub_category_name"]
        )

        existing_category = db.query(models.Category).filter(models.Category.category_id == category_id).first()

        if not existing_category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )

        if update_category.category_name is not None:
            user_obj = db.query(models.User).filter(models.User.category_id['category'].contains([{"id": category_id}])).all()
            
            #update the category name in the User model if it exists
            for user in user_obj:
                categories = user.category_id.copy() if user.category_id else {}
                updated = False
                for item in categories['category']:
                    if item.get('id') == category_id:
                        item['label'] = update_category.category_name
                        updated = True
                        break
                if updated:
                    user.category_id = categories
                    db.execute(update(models.User).where(models.User.uuid == user.uuid).values(category_id=categories))
                    db.commit()
                    db.refresh(user)                 
            existing_category.category_name = update_category.category_name

        if update_category.updated_by is not None:
            existing_category.updated_by = update_category.updated_by

        if update_category.sub_category is not None:
            for sub_category in update_category.sub_category:
                if sub_category.get("sub_category_id") != "":
                    sub_category_obj = db.query(models.SubCategory).filter(
                        models.SubCategory.sub_category_id == sub_category.get("sub_category_id"),
                        models.SubCategory.category_id == category_id
                    ).first()
                    if sub_category_obj:
                        user_obj = db.query(models.User).filter(models.User.category_id['category'].contains([{"id": category_id}, 
                        {"subCategory": [{"id": sub_category.get("sub_category_id")}]}])).all()
                        
                        for user in user_obj:
                            categories = user.category_id.copy() if user.category_id else {}
                            for item in categories['category']:
                                if item.get('id') == category_id:
                                    for sub_item in item['subCategory']:
                                        if sub_item.get('id') == sub_category.get("sub_category_id"):
                                            sub_item['label'] = sub_category.get("sub_category_name")
                                            updated = True
                                            break
                            if updated:
                                print(categories)
                                user.category_id = categories
                                db.execute(update(models.User).where(models.User.uuid == user.uuid).values(category_id=categories))
                                db.commit()
                                db.refresh(user)
                        sub_category_obj.sub_category_name = sub_category.get("sub_category_name")
                        sub_category_obj.updated_by = update_category.updated_by
                else:
                    new_sub_category = models.SubCategory(
                        sub_category_name=sub_category.get("sub_category_name"),
                        category_id=category_id,
                        created_by=update_category.updated_by,
                        is_approved=True)
                    db.add(new_sub_category)
        db.commit()
        db.refresh(existing_category)
        return {
            "category": existing_category,
            "subcategories": db.query(models.SubCategory)
            .filter(models.SubCategory.category_id == category_id)
            .all(),
        }

    except HTTPException as e:
        raise e


async def other_category(
    category_name_original: str,
    other_category_id: int | None = None,
    db: Session = Depends(get_db),
):
    try:
        category_name = await translate_fields(category_name_original, fields=[])

        existing_category = (
            db.query(models.Category)
            .filter(func.lower(models.Category.category_name) == category_name.lower())
            .first()
        )
        if existing_category:
            if existing_category.is_approved == False:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Category {category_name} has been suggested to the Platform already",
                     )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Category {category_name} already exists",
            )
        new_category = models.Category(
            category_name=category_name,
            other_category_id=other_category_id,
        )
        db.add(new_category)
        db.commit()
        db.refresh(new_category)

        return new_category
    except HTTPException as e:
        raise e
    
async def other_sub_category(
    sub_category_name: str,
    category_id: int,
    db: Session = Depends(get_db),
):
    try:
        sub_category_name = await translate_fields(sub_category_name, fields=[])
        
        existing_subcategory = (
            db.query(models.SubCategory)
            .filter(
                func.lower(models.SubCategory.sub_category_name) == sub_category_name.lower(),
                models.SubCategory.category_id == category_id,
            )
            .first()
        )
        if existing_subcategory:
            if existing_subcategory.is_approved == False:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Subcategory {sub_category_name} has been suggested to the Platform already",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subcategory {sub_category_name} already exists in category ID {category_id}",
            )
        new_subcategory = models.SubCategory(
            sub_category_name=sub_category_name,
            category_id=category_id,
            is_approved=False
        )
        db.add(new_subcategory)
        db.commit()
        db.refresh(new_subcategory)
        
        return new_subcategory
    except HTTPException as e:
        raise e


def approve_category(category_id: int,user_uuid,db: Session):
    try:
        category = (
            db.query(models.Category)
            .filter(models.Category.category_id == category_id)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )
        
        user_obj = db.query(models.User).filter(models.User.uuid == user_uuid,models.User.is_deleted == False ).first()
        
        if user_obj:
            categories = user_obj.category_id.copy() if user_obj.category_id else {}
            updated = False
            for item in categories['category']:
                if item.get('id') == category_id:
                    item['status'] = "approved"
                    updated = True
                    break
            if updated:
                user_obj.category_id = categories
                db.execute(update(models.User).where(models.User.uuid == user_uuid).values(category_id=categories))
                db.commit()
                db.refresh(user_obj)

        category.is_approved = True

        db.commit()
        db.refresh(category)

        return category

    except HTTPException as e:
        raise e


def reject_category(category_id: int, db: Session):
    try:
        category = (
            db.query(models.Category)
            .filter(models.Category.category_id == category_id)
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )

        category.is_approved = False

        db.commit()
        db.refresh(category)

        return category

    except HTTPException as e:
        raise e

def update_subcategory(data ,db: Session):
    try:
        subcategory = (
            db.query(models.SubCategory)
            .filter(models.SubCategory.sub_category_id == data.sub_category_id)
            .first()
        )
        
        if not subcategory:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found"
            )
        category = db.query(models.Category).filter(models.Category.category_id == subcategory.category_id).first()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
            )
        if category.is_approved == False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Its category is not approved yet"
            )
        user_obj = db.query(models.User).filter(models.User.uuid == data.uuid,models.User.is_deleted == False ).first()
    
        if user_obj :
            categories = user_obj.category_id.copy() if user_obj.category_id else {}
            updated = False
            for item in categories['category']:
                if item.get('subCategory'):
                    for sub_item in item['subCategory']:
                        if sub_item.get('id') == data.sub_category_id:
                            if data.status:
                                sub_item['status'] = "approved" 
                            else:
                                sub_item['status'] = "rejected" 
                            updated = True
                            break
            if updated:
                user_obj.category_id = categories
                db.execute(update(models.User).where(models.User.uuid == data.uuid).values(category_id=categories))
                db.commit()
                db.refresh(user_obj)

        
        subcategory.is_approved = data.status

        db.commit()
        db.refresh(subcategory)

        return subcategory
    
    except HTTPException as e:
        raise e

def get_approved_categories(skip,limit,db: Session):
    try:
        query = db.query(models.Category).filter(models.Category.is_approved == True)
        categories = query.offset(skip).limit(limit).all()
        total_categories = query.count()
                                                      
        for category in categories:
            subcategories = (
                db.query(models.SubCategory)
                .filter(models.SubCategory.category_id == category.category_id,models.SubCategory.is_approved == True)
                .all()
            )
            category.sub_category_name = subcategories
        categories.sort(key=lambda x: x.category_name)
        return {
            "total_categories": total_categories,
            "categories": categories,
        }

    except Exception as e:
        raise e


def get_requested_categories(skip,limit,db: Session):
    try:
        query = db.query(models.Category).filter(models.Category.is_approved == False)
        categories = query.offset(skip).limit(limit).all()
        total_categories = query.count()

        return {
            "total_categories": total_categories,
            "categories": categories,
        }

    except Exception as e:
        raise e


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ADBANNER_PATH = os.path.join(BASE_DIR, "adbanner")
os.makedirs(ADBANNER_PATH, exist_ok=True)


def save_uploaded_adbanner(
    file: UploadFile, request: Request, folder: str | None = None
) -> str | None:
    """Save uploaded file and return its full server URL."""
    if not file:
        return None

    folder = folder or ADBANNER_PATH  # Ensure it saves to the correct directory
    file_uuid = str(uuid.uuid4())
    _, ext = os.path.splitext(file.filename)
    new_filename = f"{file_uuid}_{file.filename}"
    file_path = os.path.join(folder, new_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        base_url = str(request.base_url).rstrip("/")
        return f"{base_url}/api/adbanner/{new_filename}"  # Fix URL path to match mounted directory

    except Exception as e:
        logger.log_error(f"Error saving file: {e}")
        return None


async def create_adbanner(
    request: Request,
    adbanner_original: schemas.AdBanner,
    image_url: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    try:
        adbanner = await translate_fields(
            adbanner_original, fields=["alternative_text"]
        )
        # Validate if the service provider exists
        user = (
            db.query(models.User)
            .filter(models.User.uuid == adbanner.created_by_uuid)
            .first()
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        image_url = save_uploaded_adbanner(image_url, request) if image_url else None

        # Create a new subscription instance
        new_adbanner = models.AdBanner(
            alternative_text=adbanner.alternative_text,
            category_id=adbanner.category_id,
            link=adbanner.link,
            created_by=adbanner.created_by_uuid,
            image_url=image_url,
        )

        # Add the new subscription to the session
        db.add(new_adbanner)
        db.commit()
        db.refresh(new_adbanner)

        return new_adbanner

    except HTTPException as e:
        raise e


async def update_adbanner(
    adbanner_id: int,
    request: Request,
    adbanner_original: schemas.UpdateAdBanner,
    image_url: UploadFile = None,
    db: Session = Depends(get_db),
):
    try:
        adbanner = await translate_fields(
            adbanner_original, fields=["alternative_text"]
        )

        logger.log_info(f"Received request to update ad banner with ID: {adbanner_id}")
        logger.log_info(f"Received payload: {adbanner.dict()}")
        if image_url:
            logger.log_info(f"Received image file: {image_url.filename}")

        # Fetch the existing ad banner by ID
        existing_adbanner = (
            db.query(models.AdBanner)
            .filter(models.AdBanner.adbanner_id == adbanner_id)
            .first()
        )

        if not existing_adbanner:
            logger.log_warning(f"Ad Banner with ID {adbanner_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Ad Banner not found"
            )

        # Update fields
        if adbanner.alternative_text is not None:
            logger.log_info("Updating alternative_text")
            existing_adbanner.alternative_text = adbanner.alternative_text

        if adbanner.category_id is not None:
            logger.log_info("Updating category_id")
            existing_adbanner.category_id = adbanner.category_id

        if adbanner.link is not None:
            logger.log_info("Updating link")
            existing_adbanner.link = adbanner.link

        # Handle image upload
        if image_url is not None:
            logger.log_info("Processing image upload")
            image_path = save_uploaded_adbanner(image_url, request, "adbanner")
            existing_adbanner.image_url = image_path
            logger.log_info(f"Image saved at: {image_path}")

        if adbanner.updated_by_uuid is not None:
            try:
                logger.log_info("Updating updated_by_uuid")
                existing_adbanner.updated_by = adbanner.updated_by_uuid
            except ValueError:
                logger.log_error("Invalid UUID format for updated_by_uuid")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid UUID for updated_by_uuid",
                )

        # Commit changes to DB
        logger.log_info(f"Committing changes to database")
        db.commit()
        db.refresh(existing_adbanner)

        logger.log_info(f"Ad Banner with ID {adbanner_id} updated successfully")
        return existing_adbanner

    except HTTPException as e:
        logger.log_error(f"HTTP Exception: {e.detail}")
        raise e
    except Exception as e:
        logger.exception("Unexpected error occurred")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e!s}",
        )


def adbanner_status(adbanner_id: int, db: Session):
    try:
        adbanner = (
            db.query(models.AdBanner)
            .filter(models.AdBanner.adbanner_id == adbanner_id)
            .first()
        )
        if not adbanner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Ad Banner not found"
            )

        adbanner.is_activated = not adbanner.is_activated
        db.commit()
        db.refresh(adbanner)

        # status = "activated" if adbanner.is_activated else "deactivated"
        return {
            "detail": "Sub Admin status toggled successfully",
            "is_activated": adbanner.is_activated,
        }

    except HTTPException as e:
        raise e


def delete_adbanner(adbanner_id: int, db: Session):
    try:
        adbanner = (
            db.query(models.AdBanner)
            .filter(models.AdBanner.adbanner_id == adbanner_id)
            .first()
        )
        if adbanner is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Ad/Banner is not found"
            )
        db.delete(adbanner)
        db.commit()
        return {"detail": f"Ad/Banner with ID {adbanner_id} has been deleted."}
    except HTTPException as e:
        raise e


async def get_all_adbanner(
    skip: int, limit: int, db: Session, alternative_text_original: str = None
):
    try:
        alternative_text = await translate_fields(alternative_text_original, fields=[])

        query = db.query(
            models.AdBanner.adbanner_id,
            models.AdBanner.created_by,  # Use created_by instead of created_by_uuid
            models.AdBanner.alternative_text,
            models.AdBanner.category_id,
            models.Category.category_name.label("category_name"),  # Get category name
            models.AdBanner.link,
            models.AdBanner.image_url,
            models.AdBanner.created_at,
            models.AdBanner.updated_at,
            models.AdBanner.is_activated,
        ).join(
            models.Category, models.AdBanner.category_id == models.Category.category_id
        )

        if alternative_text:
            query = query.filter(
                models.AdBanner.alternative_text.ilike(f"%{alternative_text}%")
            )

        adbanners = query.offset(skip).limit(limit).all()
        total_adbanners = query.count()

        return {
            "total_adbanners": total_adbanners,
            "all_adbanners": [
                adbanner._asdict()  # Convert named tuple to dictionary for safer access
                for adbanner in adbanners
            ],
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e!s}",
        )


async def create_broadcast(
    broadcast_original: schemas.BroadcastMessageCreate, db: Session = Depends(get_db)
):
    broadcast = await translate_fields(broadcast_original, fields=["title", "message"])

    # Convert UUIDs to strings
    broadcast_dict = broadcast.dict()
    broadcast_dict["recipients"] = [str(uuid) for uuid in broadcast.recipients]

    # Save the broadcast message in the database
    db_broadcast = models.BroadcastMessage(**broadcast_dict)
    db.add(db_broadcast)
    db.commit()
    db.refresh(db_broadcast)

    # Send real-time notification and save notification record
    for recipient in broadcast.recipients:
        # Save notification in the database
        notification = models.Notification(
            user_id=str(recipient),
            title="New Broadcast Message",
            message=broadcast.message,
            is_read=False,
            type="BROADCAST_NOTIFICATION_SEND",
        )
        db.add(notification)

        # Send WebSocket notification
        try:
            # await manager.send_to_user(str(recipient), {
            #     "recipient":recipient,
            #     "type": "BROADCAST_NOTIFICATION_SEND",
            #     "broadcast_id": str(db_broadcast.broadcast_id),
            #     "message": broadcast.message
            # })

            await manager.send_to_user(
                str(recipient),
                json.dumps(
                    {
                        "recipient": recipient,
                        "type": "BROADCAST_NOTIFICATION_SEND",
                        "message": broadcast.message,
                    }
                ),
            )
        except Exception as e:
            logger.log_error(f"Failed to send WebSocket message to {recipient}: {e!s}")

    db.commit()  # Commit all notifications at once for efficiency

    return db_broadcast


def read_broadcast(broadcast_id: int, db: Session = Depends(get_db)):
    broadcast = (
        db.query(models.BroadcastMessage)
        .filter(models.BroadcastMessage.broadcast_id == broadcast_id)
        .first()
    )
    if broadcast is None:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    # Convert recipient strings back to UUIDs
    broadcast.recipients = [UUID(recipient) for recipient in broadcast.recipients]

    return broadcast


async def get_all_broadcast(
    user_id: UUID4, skip: int, limit: int, db: Session, title_original: str = None
):
    try:
        title = await translate_fields(title_original, fields=[])

        user = db.query(models.User).filter(models.User.uuid == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Base query
        if user.role_type == "admin":
            query = db.query(models.BroadcastMessage)
        else:
            query = db.query(models.BroadcastMessage).filter(
                models.BroadcastMessage.recipients.contains([str(user_id)])
            )

        # Apply title or message search
        if title:
            query = query.filter(
                or_(
                    models.BroadcastMessage.title.ilike(f"%{title}%"),
                    models.BroadcastMessage.message.ilike(f"%{title}%"),
                )
            )
        query = query.order_by(models.BroadcastMessage.created_at.desc())
        total_broadcasts = query.count()
        broadcast_messages = query.offset(skip).limit(limit).all()

        broadcasts_result = []

        for msg in broadcast_messages:
            recipient_ids = msg.recipients if isinstance(msg.recipients, list) else []
            users = (
                db.query(models.User).filter(models.User.uuid.in_(recipient_ids)).all()
            )
            user_mapping = {str(u.uuid): u for u in users}

            recipients_list = []
            for rid in recipient_ids:
                rid_str = str(rid)
                if rid_str in user_mapping:
                    r_user = user_mapping[rid_str]
                    sp_details = r_user.details.get("service_provider", {})
                    recipients_list.append(
                        {
                            "uuid": rid_str,
                            "name": sp_details.get("name"),
                            "founder_first_name": sp_details.get("founder_first_name"),
                            "founder_last_name": sp_details.get("founder_last_name"),
                            "profile_img": r_user.profile_img,
                        }
                    )
                else:
                    recipients_list.append(
                        {
                            "uuid": rid_str,
                            "name": None,
                            "founder_first_name": None,
                            "founder_last_name": None,
                            "profile_img": None,
                        }
                    )

            broadcasts_result.append(
                {
                    "title": msg.title,
                    "message": msg.message,
                    "broadcast_id": msg.broadcast_id,
                    "created_by": msg.created_by,
                    "created_at": msg.created_at,
                    "recipients": recipients_list,
                }
            )

        return {"total_broadcasts": total_broadcasts, "broadcasts": broadcasts_result}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e!s}",
        )


def delete_broadcast(broadcast_id: int, db: Session):
    try:
        broadcast = (
            db.query(models.BroadcastMessage)
            .filter(models.BroadcastMessage.broadcast_id == broadcast_id)
            .first()
        )
        if broadcast is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Broadcast is not found"
            )
        db.delete(broadcast)
        db.commit()
        return {"detail": f"Broadcast of id {broadcast_id} is deleted successfully"}
    except HTTPException as e:
        raise e


async def create_admin(admin: schemas.Admin, db: Session = Depends(get_db)):
    try:
        existing_user = (
            db.query(models.User)
            .filter(models.User.useremail == admin.useremail)
            .first()
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address already exists",
            )

        encrypted_password = encrypt_password(admin.password, secret_key)
        new_admin = models.User(
            useremail=admin.useremail,
            password=encrypted_password,
            role_type="admin",
            is_activated=True,
            status="verified",
            created_by=None,
            details={"admin": {"name": admin.name}},
            permission={
                "admin": {
                    "can_create_subadmin": True,
                    "can_edit_subadmin": True,
                    "can_delete_subadmin": True,
                }
            },
        )
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        return new_admin

    except HTTPException as e:
        return e


def generate_report(db: Session):
    """Generate CSV report for revenue data from the Membership table"""

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
    # Query Memberships with relevant details
    memberships = (
        db.query(
            models.User.profile_img,
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

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(
        [
            "Profile",
            "Provider",
            "Purchase Date",
            "Expiry Date",
            "Subscription Plan",
            "Amount Collected",
        ]
    )

    # Write membership data
    for membership in memberships:
        writer.writerow(
            [
                membership.profile_img if membership.profile_img else "N/A",
                membership.provider_name or "Unknown",
                membership.latest_billing_date.strftime("%Y-%m-%d")
                if membership.latest_billing_date
                else "N/A",
                membership.expiry_date.strftime("%Y-%m-%d")
                if membership.expiry_date
                else "N/A",
                membership.subscription_name,
                membership.total_amount or 0,
            ]
        )

    # Return CSV response
    response = Response(content=output.getvalue(), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=revenue_report.csv"

    return response


async def add_rating_question(question_original: schemas.RatingQuestion, db: Session):
    question = await translate_fields(
        question_original, fields=["question_text", "target_user"]
    )

    user = db.query(models.User).filter(models.User.uuid == question.user_id).first()

    if not (
        user.role_type == "admin"
        or (
            user.role_type == "sub_admin"
            and user.permission.get("sub_admin", {})
            .get("quetionaries", {})
            .get("add", False)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized to create a question",
        )

    existing_question = (
        db.query(models.RatingQuestion)
        .filter(models.RatingQuestion.question_text == question.question_text)
        .first()
    )

    if existing_question:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This question already exist"
        )

    new_question = models.RatingQuestion(
        question_text=question.question_text,
        target_user=question.target_user,
        chronological_order=question.chronological_order,
        created_by=question.user_id,
        is_mandatory=question.is_mandatory,
    )

    db.add(new_question)
    db.commit()
    db.refresh(new_question)

    return {
        "question_text": question.question_text,
        "target_user": question.target_user,
        "chronological_order": question.chronological_order,
    }


async def update_rating_question(
    question_original: schemas.UpdateRatingQuestion, db: Session
):
    question = await translate_fields(
        question_original, fields=["question_text", "target_user"]
    )

    user = db.query(models.User).filter(models.User.uuid == question.updated_by).first()

    if not (
        user.role_type == "admin"
        or (
            user.role_type == "sub_admin"
            and user.permission.get("sub_admin", {})
            .get("quetionaries", {})
            .get("edit", False)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized to edit a question",
        )

    existing_question = (
        db.query(models.RatingQuestion)
        .filter(models.RatingQuestion.question_id == question.question_id)
        .first()
    )

    if not existing_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )

    if question.question_text is not None:
        existing_question.question_text = question.question_text
    if question.target_user is not None:
        existing_question.target_user = question.target_user
    if question.chronological_order is not None:
        existing_question.chronological_order = question.chronological_order
    if question.is_mandatory is not None:
        existing_question.is_mandatory = question.is_mandatory

    existing_question.updated_by = question.updated_by

    db.commit()
    db.refresh(existing_question)

    return {"existing_question": existing_question, "updated_by": question.updated_by}


def delete_rating_question(question_id: int, deleted_by: UUID, db: Session):
    user = db.query(models.User).filter(models.User.uuid == deleted_by).first()

    if not (
        user.role_type == "admin"
        or (
            user.role_type == "sub_admin"
            and user.permission.get("sub_admin", {})
            .get("quetionaries", {})
            .get("edit", False)
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You are not authorized to edit a question",
        )

    existing_question = (
        db.query(models.RatingQuestion)
        .filter(models.RatingQuestion.question_id == question_id)
        .first()
    )

    if not existing_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Question not found"
        )

    existing_question.deleted_by = deleted_by
    existing_question.is_deleted = True

    db.commit()
    db.refresh(existing_question)

    return {"Question is sucessfully deleted"}


async def get_rating_question(
    skip: int,
    limit: int,
    db: Session,
    target_user: str = None,
    question_text_original: str = None,
):
    question_text = await translate_fields(question_text_original, fields=[])

    questions = db.query(models.RatingQuestion).filter(
        models.RatingQuestion.is_deleted == False
    )

    if target_user:
        questions = questions.filter(models.RatingQuestion.target_user == target_user)

    if question_text:
        questions = questions.filter(
            models.RatingQuestion.question_text.ilike(f"%{question_text}%")
        )

    questions = questions.order_by(
        models.RatingQuestion.chronological_order.asc(),
        models.RatingQuestion.created_at.desc(),
    )

    total_questions = questions.count()
    paginated_question = questions.offset(skip).limit(limit).all()

    for idx, q in enumerate(paginated_question, start=1):
        q.chronological_order = idx

    return {"questions": paginated_question, "total_questions": total_questions}


async def get_all_questionnaires(db: Session = None):
    get_questionnaires = db.query(models.Questionnaires).first()
    return get_questionnaires.data


async def add_questionnaires(data, db: Session):
    new_questionnaires = models.Questionnaires(
        id=uuid.uuid4(),
        data=data,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Add the new questionnaire to the session
    db.add(new_questionnaires)
    db.commit()

    return {"status": 200, "details": "Questionnaires added successfully"}


async def delete_questionnaires(db: Session):
    get_questionnaires = db.query(models.Questionnaires).first()

    if not get_questionnaires:
        return {"status": 404, "details": "Questionnaire not found"}

    db.delete(get_questionnaires)
    db.commit()

    return {"status": 200, "details": "Questionnaires deleted successfully"}


async def update_questionnaires(data, db: Session):
    if not isinstance(data, dict):
        return {"status": 400, "details": "Data must be a dictionary."}

    get_questionnaires = db.query(models.Questionnaires).first()

    if not get_questionnaires:
        return {"status": 404, "details": "Questionnaires not found."}

    get_questionnaires.data = data
    get_questionnaires.updated_at = datetime.utcnow()

    db.commit()

    return {"status": 200, "details": "Questionnaire updated successfully"}


def create_faq(faq: schemas.FAQCreate, db: Session = Depends(get_db)):
    
    try :

        get_admin = db.query(models.User).filter(models.User.uuid == faq.created_by,models.User.role_type == 'admin').first()

        if not get_admin:
            return {
                "status": 404,
                "detail": "Please provide a correct admin UUID",
            }
        
        
        for f in faq.details:
            if not f.get("question") or not f.get("answer"):
                return {
                    "status": 400,
                    "detail": "Question and answer cannot be empty",
                }
            new_faq = models.Faq(
                question = f["question"],
                answer = f["answer"],
                created_by = faq.created_by,
                role_type = faq.role_type
            )
                
            db.add(new_faq)
        db.commit()
         
        return {
            "status": 200,
            "detail": "FAQs created successfully",
        }
    except HTTPException as e:
        return {
            "status":404,
            "detail": f"Error creating FAQ: {e.detail}"
        }

def get_faqs(skip, limit, db, role_type=None):
    try:
        faqs = db.query(models.Faq)
        if role_type:
            faqs = faqs.filter(models.Faq.role_type == role_type)
        else:
            faqs = faqs.offset(skip).limit(limit).all()
        if not faqs:
            return {"status": 404, "detail": "No FAQs found"}
        return {"status": 200, "faqs": faqs.all(), "total": faqs.count()}
    except HTTPException as e:
        return {
            "status": 404,
            "detail": f"Error fetching FAQs: {e.detail}"
        }

def update_faq(faq_id: int, faq: schemas.FAQUpdate, db: Session = Depends(get_db)):
    try:
        existing_faq = db.query(models.Faq).filter(models.Faq.faq_id == faq_id).first()

        if not existing_faq:
            return {
                "status": 404,
                "detail": "FAQ not found"
            }
        
        if faq.question is not None:
            existing_faq.question = faq.question
        if faq.answer is not None:
            existing_faq.answer = faq.answer
        if faq.updated_by is not None:
            existing_faq.updated_by = faq.updated_by
            existing_faq.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(existing_faq)

        return {
            "status": 200,
            "detail": "FAQ updated successfully",
            "faq": existing_faq
        }
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error fetching FAQ: {e}"
        }

def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    try:
        existing_faq = db.query(models.Faq).filter(models.Faq.faq_id == faq_id).first()

        if not existing_faq:
            return {
                "status": 404,
                "detail": "FAQ not found"
            }
        
        db.delete(existing_faq)
        db.commit()

        return {
            "status": 200,
            "detail": "FAQ deleted successfully"
        }
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error deleting FAQ: {e}"
        }
    
def get_organization_type(skip,limit,db):
    try:
        org_types = db.query(models.OrganizationType)
        query = org_types.offset(skip).limit(limit).all()
        if not org_types:
            return {"status": 404, "detail": "No organization types found"}
        
        return {"status": 200, "organization_types": query,"total":org_types.count()}
    except HTTPException as e:
        return {
            "status": 404,
            "detail": f"Error fetching organization types: {e.detail}"
        }


def create_organization_type(org_type: schemas.OrganizationTypeCreate, db: Session = Depends(get_db)):

    try :
        for organization in org_type.name:
            existing_org_type = db.query(models.OrganizationType).filter(models.OrganizationType.name == organization).first()
            if not existing_org_type:
                new_org_type = models.OrganizationType(
                    name=organization,
                    created_by=org_type.created_by
                )
                db.add(new_org_type)
        db.commit()

        return {
            "status": 200,
            "detail": "Organization types created successfully"
        }
    
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error creating organization type: {e}"
        }


def delete_organization_type(org_type_id: int, db: Session = Depends(get_db)):
    try:
        existing_org_type = db.query(models.OrganizationType).filter(models.OrganizationType.id == org_type_id).first()

        if not existing_org_type:
            return {
                "status": 404,
                "detail": "Organization type not found"
            }
        service_provider = db.query(models.User).filter(cast(models.User.details["service_provider"]["organization_type"].astext,String,)== str(existing_org_type.name)).count()
        if service_provider >= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This organization cannot be deleted because it is associated with one or more service providers.",
            )
        db.delete(existing_org_type)
        db.commit()

        return {
            "status": 200,
            "detail": "Organization type deleted successfully"
        }
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error deleting organization type: {e}"
        }

def update_organization_type(
    org_type_id: int, org_type: schemas.OrganizationTypeUpdate, db: Session = Depends(get_db)
):
    try:
        existing_org_type = db.query(models.OrganizationType).filter(models.OrganizationType.id == org_type_id).first()

        if not existing_org_type:
            return {
                "status": 404,
                "detail": "Organization type not found"
            }
        
        if org_type.name is not None:
            existing_org_type.name = org_type.name
        if org_type.updated_by is not None:
            existing_org_type.updated_by = org_type.updated_by
            existing_org_type.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(existing_org_type)

        return {
            "status": 200,
            "detail": "Organization type updated successfully",
            "organization_type": existing_org_type
        }
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error updating organization type: {e}"
        }

def create_site_settings(
    site_settings: schemas.SiteSettingsCreate, db: Session = Depends(get_db)
):
    try:
        existing_setting = db.query(models.SiteSettings).first()
        
        if existing_setting:
            return {
                "status": 409,
                "detail": "Site settings already exist"
            }
        
        new_setting = models.SiteSettings(
            site_name=site_settings.site_name,
            website_link=site_settings.website_link,
            contact_email=site_settings.contact_email,
            contact_number=site_settings.contact_number,
            address=site_settings.address
        )
        
        db.add(new_setting)
        db.commit()

        return {
            "status": 200,
            "detail": "Site settings created successfully",
            "site_settings": new_setting
        }
    
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error creating site settings: {e}"
        }

def get_site_settings(db: Session = Depends(get_db)):
    try:
        site_settings = db.query(models.SiteSettings).first()
        
        if not site_settings:
            return {
                "status": 404,
                "detail": "Site settings not found"
            }
        
        return {
            "status": 200,
            "site_settings": site_settings
        }
    
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error fetching site settings: {e}"
        }

def update_site_settings(
    site_settings: schemas.SiteSettingsCreate, db: Session = Depends(get_db)
):
    try:
        existing_setting = db.query(models.SiteSettings).first()
        
        if not existing_setting:
            return {
                "status": 404,
                "detail": "Site settings not found"
            }
        
        if site_settings.site_name is not None:
            existing_setting.site_name = site_settings.site_name
        if site_settings.website_link is not None:
            existing_setting.website_link = site_settings.website_link
        if site_settings.contact_email is not None:
            existing_setting.contact_email = site_settings.contact_email
        if site_settings.contact_number is not None:
            existing_setting.contact_number = site_settings.contact_number
        if site_settings.address is not None:
            existing_setting.address = site_settings.address
        
        db.commit()
        db.refresh(existing_setting)

        return {
            "status": 200,
            "detail": "Site settings updated successfully",
            "site_settings": existing_setting
        }
    
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error updating site settings: {e}"
        }

def delete_site_settings(db: Session = Depends(get_db)):
    try:
        existing_setting = db.query(models.SiteSettings).first()
        
        if not existing_setting:
            return {
                "status": 404,
                "detail": "Site settings not found"
            }
        
        db.delete(existing_setting)
        db.commit()

        return {
            "status": 200,
            "detail": "Site settings deleted successfully"
        }
    
    except Exception as e:
        return {
            "status": 404,
            "detail": f"Error deleting site settings: {e}"
        }

def export_data(db:Session = Depends(get_db),id:UUID4 = None):
    pass
    