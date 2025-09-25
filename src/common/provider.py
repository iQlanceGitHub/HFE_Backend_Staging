import calendar
import json
import os
import uuid
from datetime import datetime, timedelta

import stripe
from fastapi import Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import UUID4, EmailStr
from sqlalchemy import UUID, and_, func, or_, update
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: F811
from sqlalchemy.orm import Session, class_mapper
from sqlalchemy.orm.attributes import flag_modified

from src.api import schemas
from src.api.schemas import CreateServiceProvider
from src.authentication.encryption import decrypt_password, encrypt_password, secret_key
from src.common.email_service import send_email
from src.common.translate import translate_fields
from src.common.user import save_uploaded_file, save_uploaded_pdf
from src.configs import database
from src.configs.config import logger
from src.models import models
from src.routers.chat import manager

get_db = database.get_db

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AVATAR_DIR = os.path.join(BASE_DIR, "avatars")


def model_to_dict(model_instance):
    return {
        column.name: getattr(model_instance, column.name)
        for column in class_mapper(model_instance.__class__).columns
    }


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


async def create_service_provder_self(
    request: Request,
    provider_original: CreateServiceProvider,
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    brochure: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    try:
        provider = await translate_fields(
            provider_original,
            fields=[
                "name",
                "organization_type",
                "contact_title",
                "contact_name",
                "founder_first_name",
                "founder_last_name",
                "address_1",
                "address_2",
                "county",
                "city",
                "country",
                "state",
                "gender",
                "question",
                "description",
                "keywords",
            ],
        )

        service_provider = (
            db.query(models.User)
            .filter(models.User.useremail == provider.email)
            .first()
        )

        if service_provider and service_provider.is_deleted == False:
            return JSONResponse(
                status_code=400, content={"message": "Email already exists"}
            )

        if profile_img:
            allowed_types = ["image/jpeg", "image/png"]
            if profile_img.content_type not in allowed_types:
                return JSONResponse(
                    tatus_code=400,
                    content={
                        "message": "Invalid file type for profile image. Only JPG and PNG files are allowed."
                    },
                )

        # Process profile and header images
        profile_img_url = (
            save_uploaded_file(profile_img, request) if profile_img else None
        )

        if header_img:
            allowed_types = ["image/jpeg", "image/png"]
            if header_img.content_type not in allowed_types:
                return JSONResponse(
                    status_code=400,
                    content={
                        "message": "Invalid file type for cover image. Only JPG and PNG files are allowed."
                    },
                )

        header_img_url = save_uploaded_file(header_img, request) if header_img else None
        brochure_url = (
            save_uploaded_pdf(brochure, request, folder="brochure", mount="brochure")
            if brochure
            else None
        )
        encrypted_password = encrypt_password(provider.password, secret_key)
        new_provider = models.User(
            useremail=provider.email,
            password=encrypted_password,
            role_type="service_provider",
            # service_provider_type = provider.service_provider_type,
            profile_img=profile_img_url,
            header_img=header_img_url,
            is_activated=False,
            is_claimed=True,
            is_imported=False,
            status="pending",
            details={
                "service_provider": {
                    "name": provider.name,
                    "estimated_clients": provider.estimated_clients,
                    "organization_type": provider.organization_type,
                    "tax_id": provider.tax_id,
                    "contact_title": provider.contact_title,
                    "contact_email": provider.contact_email,
                    "contact_name": provider.contact_name,
                    "founder_first_name": provider.founder_first_name,
                    "founder_last_name": provider.founder_last_name,
                    "address_1": provider.address_1,
                    "address_2": provider.address_2,
                    "county": provider.county,
                    "city": provider.city,
                    "state": provider.state,
                    "country": provider.country,
                    "zip_code": provider.zip_code,
                    "region": provider.region,
                    "lat": provider.lat,
                    "long": provider.long,
                    "phone": provider.phone,
                    "email": provider.email,
                    "gender": provider.gender,
                    "socialmedia_links": provider.socialmedia_links,
                    "website_link": provider.website_link,
                    "question": provider.question,
                    "description": provider.description,
                    "brochure": brochure_url,
                    "client_count": 0,
                    "keywords": provider.keywords
                }
            },
            category_id = json.loads(provider.categories) if provider.categories else None                                  
        )
        db.add(new_provider)
        db.flush()

        new_provider.created_by = new_provider.uuid
        stripe_customer = stripe.Customer.create(
            name=provider.name, email=provider.email
        )
        new_provider.stripe_customer_id = stripe_customer.id

        db.commit()
        db.refresh(new_provider)

        admins = db.query(models.User).filter(models.User.role_type == "admin").all()

        for admin in admins:
            notification = models.Notification(
                user_id=str(admin.uuid),  # Client who should receive the notification
                title=f"New Service Provider SignUp_{new_provider.uuid}",
                message=f"{provider.name} has Signed Up as Service Provider",
                is_read=False,
                type="New_Provider_SignUp_Notification",
            )
            db.add(notification)
            db.commit()
            db.refresh(notification)
            logger.log_info(
                f"Added signup notification for the serviceprovider for admin: {admin.useremail}"
            )
        return model_to_dict(new_provider)
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"message": f"Internal server error: {e!s}"}
        )


async def update_service_provider_self(
    uuid: UUID,
    request: Request,
    email : EmailStr,
    updated_service_provider_original: schemas.UpdateServiceProvider,
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    brochure: UploadFile | str | None = File(None),
    db: Session = Depends(get_db),
):
    try:
        updated_service_provider = await translate_fields(
            updated_service_provider_original,
            fields=[
                "name",
                "organization_type",
                "contact_title",
                "contact_name",
                "founder_first_name",
                "founder_last_name",
                "address_1",
                "address_2",
                "county",
                "city",
                "country",
                "state",
                "gender",
                "question",
                "description",
            ],
        )

        service_provider = (
            db.query(models.User).filter(models.User.uuid == uuid).first()
        )
        if not service_provider:
            return JSONResponse(
                status_code=404, content={"message": "Service provider not found"}
            )

        updated_provider = updated_service_provider.model_dump(exclude_unset=True)
        update_data = {"updated_by": updated_service_provider.updated_by}
        profile_img_url = service_provider.profile_img
        header_img_url = service_provider.header_img
        brochure_url = service_provider.details.get("service_provider", {}).get(
            "brochure", None
        )

        if profile_img:
            profile_img_url = save_uploaded_file(profile_img, request, "hfe_images")

        if header_img:
            header_img_url = save_uploaded_file(header_img, request, "hfe_images")

        details = service_provider.details.get("service_provider", {})

        if brochure is None and brochure_url is not None:
            details["brochure"] = None
        elif brochure is not None:
            brochure_url = save_uploaded_pdf(brochure, request, folder="brochure", mount="brochure")
            if brochure_url:
                details["brochure"] = brochure_url

        # Update profile and header images if they have changed
        if profile_img_url != service_provider.profile_img:
            update_data["profile_img"] = profile_img_url
            details["profile_pic"] = profile_img_url

        if header_img_url != service_provider.header_img:
            update_data["header_img"] = header_img_url
            details["header_image"] = header_img_url


        if email:
            update_data['useremail']=email

        category_obj = None
        sub_category_obj = None

        # Update category_id and category_name only if provided
        if (
            "category_id" in updated_provider
            and updated_provider["category_id"] is not None
        ):
            category_id = updated_provider["category_id"]
            details["category_id"] = category_id
            category_obj = (
                db.query(models.Category)
                .filter(models.Category.category_id == category_id)
                .first()
            )
            details["category_name"] = (
                category_obj.category_name if category_obj else None
            )

        # Update sub_category_id and sub_category_name only if provided
        if (
            "sub_category_id" in updated_provider
            and updated_provider["sub_category_id"] is not None
        ):
            sub_category_id = updated_provider["sub_category_id"]
            details["sub_category_id"] = sub_category_id
            sub_category_obj = (
                db.query(models.SubCategory)
                .filter(models.SubCategory.sub_category_id == sub_category_id)
                .first()
            )
            details["sub_category_name"] = (
                sub_category_obj.sub_category_name if sub_category_obj else None
            )

        # Update other details fields
        for key, value in updated_provider.items():
            if key not in ["category_id", "sub_category_id"]:
                details[key] = value

        # Update the JSONB "details" column by replacing the "service_provider" key entirely.
        db.query(models.User).filter(models.User.uuid == uuid).update(
            {
                "details": func.jsonb_set(
                    models.User.details,
                    "{service_provider}",  # path to the nested object
                    json.dumps(details, default=str),
                    True,  # create_missing = True
                )
            }
        )

        # Commit after updating details to avoid issues
        db.commit()

        # Update service_provider_type if changed
        if (
            "service_provider_type" in updated_provider
            and updated_provider["service_provider_type"] is not None
        ):
            update_data["service_provider_type"] = updated_provider[
                "service_provider_type"
            ]
        else:
            update_data["service_provider_type"] = (
                service_provider.service_provider_type or "individual"
            )

        # Apply other updates if necessary
        if update_data:
            db.query(models.User).filter(models.User.uuid == uuid).update(update_data)
        if updated_provider['categories']:
            categories = json.loads(updated_provider['categories'])
            db.query(models.User).filter(models.User.uuid == uuid).update(
                {"category_id": categories}
            )
        user_obj = db.query(models.User).filter(models.User.uuid == uuid).first()
         
        #update the stripe customer details
        if user_obj.stripe_customer_id is None and user_obj.is_imported == True:
            encrypted_password = encrypt_password(updated_service_provider_original.password, secret_key)
            stripe_customer = stripe.Customer.create(
            name=updated_service_provider.name, email=user_obj.useremail
        )
            user_obj.stripe_customer_id = stripe_customer.id
            user_obj.password = encrypted_password
        if user_obj.is_claimed == False:
            user_obj.is_claimed = True
        # Commit again to save other updates
        db.commit()
        db.refresh(service_provider)

        return service_provider

    except HTTPException as e:
        raise e


async def create_staff(
    request: Request,
    staff_original: schemas.ProviderStaff,
    profile_img: UploadFile = File(None),
    header_image: UploadFile = File(None),
    avatar_selection: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        staff = await translate_fields(
            staff_original, fields=["first_name", "last_name", "gender", "description"]
        )

        # ✅ Log the received payload using Pydantic's dict()
        logger.log_info(f"Received payload: {staff.dict()}")
        encrypted_password = encrypt_password(staff.password, secret_key)

        # ✅ Log uploaded images details
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

        # Check if sub-admin already exists
        existing_subadmin = (
            db.query(models.User)
            .filter(models.User.useremail == staff.useremail)
            .first()
        )
        if existing_subadmin:
            if not existing_subadmin.is_deleted:
                logger.log_warning(
                    f"Sub-admin with email {staff.useremail} already exists."
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Sub Admin with {staff.useremail} already exists and is active.",
                )
            logger.log_info(
                f"Sub-admin {staff.useremail} exists but was marked as deleted. Reusing the email."
            )

        # Process profile and header images
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
        new_staff = models.User(
            uuid=new_uuid,
            created_by=staff.uuid,
            useremail=staff.useremail,
            password=encrypted_password,
            role_type="staff",
            profile_img=profile_img_url,
            header_img=header_img_url,
            is_activated=True,
            status="verified",
            details={
                "service_provider": {
                    "staff_first_name": staff.first_name,
                    "staff_last_name": staff.last_name,
                    "gender": staff.gender or "Male",
                    "phone": staff.phone,
                    "email": staff.useremail,
                }
            },
            permission=staff.permission,
        )
        db.add(new_staff)
        db.commit()
        db.refresh(new_staff)
        logger.log_info(f"Sub-admin {staff.useremail} created successfully.")

        # Sending welcome email
        subject = "Welcome to the Platform!"
        body = f"""
        <html>
            <body>
                <h1>Welcome, {staff.first_name} {staff.last_name}!</h1>
                <p>You have been added as a subadmin on our platform.</p>
                <p>Your login credentials are:</p>
                <ul>
                    <li><strong>Email:</strong> {staff.useremail}</li>
                    <li><strong>Password:</strong> {staff.password}</li>
                </ul>
                <p>Please log in and change your password immediately.</p>
                <p>Regards,</p>
                <p>The Admin Team</p>
            </body>
        </html>
        """
        await send_email(staff.useremail, subject, body)
        logger.log_info(f"Welcome email sent to {staff.useremail}")

        return {
            "uuid": new_staff.uuid,
            "first_name": staff.first_name,
            "last_name": staff.last_name,
            "phone": staff.phone,
            "gender": staff.gender or "Male",
            "useremail": staff.useremail,
            "profile_img": profile_img_url,
            "permission": staff.permission,
            "created_by": staff.uuid,
        }

    except HTTPException as e:
        logger.log_error(f"HTTP Exception: {e.detail}")
        raise e

    except Exception:
        logger.exception("An unexpected error occurred while creating the sub-admin.")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def get_all_staff(
    skip: int,
    limit: int,
    db: Session,
    name_original: str = None,
    created_by: UUID = None,
):
    try:
        name = await translate_fields(name_original, fields=[])

        query = (
            db.query(models.User)
            .filter(models.User.role_type == "staff", models.User.is_deleted == False)
            .order_by(models.User.created_at.desc())
        )

        if name:
            query = query.filter(
                models.User.details["service_provider"][
                    "staff_first_name"
                ].astext.ilike(f"%{name}%")
                | models.User.details["service_provider"][
                    "staff_last_name"
                ].astext.ilike(f"%{name}%")
            )
        if created_by:
            query = query.filter(models.User.created_by == (f"{created_by}"))
        staffs = query.offset(skip).limit(limit).all()
        total_staffs = query.count()

        formatted_staffs = [
            {
                "uuid": str(staff.uuid),
                "first_name": staff.details.get("service_provider", {}).get(
                    "staff_first_name", ""
                ),
                "last_name": staff.details.get("service_provider", {}).get(
                    "staff_last_name", ""
                ),
                "phone": staff.details.get("service_provider", {}).get("phone", ""),
                "useremail": staff.useremail,
                "profile_img": staff.profile_img if staff.profile_img else None,
                "is_activated": staff.is_activated,
                "created_by": staff.created_by,
                "created_at": staff.created_at,
                "updated_at": staff.updated_at,
                "is_deleted": staff.is_deleted,
                "updated_by": staff.updated_by,
                "deleted_by": staff.deleted_by,
                "deleted_at": staff.deleted_at,
                "header_img": staff.header_img if staff.header_img else None,
                "password": staff.password,
                "role_type": staff.role_type,
                "permission": staff.permission,
                "gender": staff.details.get("service_provider", {}).get("gender", ""),
                "status": staff.status,
            }
            for staff in staffs
        ]

        return {"total_staff": total_staffs, "staffs": formatted_staffs}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {e!s}",
        )


def get_provider_staff(staff_uuid: uuid, db: Session):
    try:
        staff = db.query(models.User).filter(models.User.uuid == staff_uuid).first()
        if not staff:
            return JSONResponse(status_code=404, content="Sub Admin not found")
        decrypted_password = decrypt_password(staff.password, secret_key)
        profile_img_path = staff.profile_img if staff.profile_img else None
        header_img_path = staff.header_img if staff.header_img else None

        return {
            "uuid": staff.uuid,
            "first_name": staff.details.get("service_provider", {}).get(
                "staff_first_name", ""
            ),
            "last_name": staff.details.get("service_provider", {}).get(
                "staff_last_name", ""
            ),
            "phone": staff.details.get("service_provider", {}).get("phone", ""),
            "useremail": staff.useremail,
            "gender": staff.details.get("service_provider", {}).get("gender", ""),
            "permission": staff.permission,
            "profile_img": profile_img_path,
            "created_by": staff.created_by,
            "is_activated": staff.is_activated,
            "header_img": header_img_path,
            "password": decrypted_password,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


async def staff_status(staff_uuid: str, db: Session):
    try:
        staff_uuid = uuid.UUID(staff_uuid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")
    try:
        del_staff = db.query(models.User).filter(models.User.uuid == staff_uuid).first()

        if del_staff is None:
            raise HTTPException(status_code=404, detail="Sub Admin not found")
        del_staff.is_activated = not del_staff.is_activated
        db.commit()
        status = "activated" if del_staff.is_activated else "deactivated"
        return {
            "detail": "Staff status toggled successfully",
            "is_activated": del_staff.is_activated,
            "status": status,
        }

    except HTTPException as e:
        raise e


async def update_staff(
    uuid: UUID,
    request: Request,
    useremail :EmailStr,
    update_original: schemas.editProviderStaff,
    profile_img: UploadFile | None = None,
    header_image: UploadFile | None = None,
    avatar_selection: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        update = await translate_fields(
            update_original, fields=["first_name", "last_name", "gender", "description"]
        )

        logger.log_info(f"Received payload: {update.model_dump()}")

        # Fetch the subadmin from the database
        staff = db.query(models.User).filter(models.User.uuid == uuid).first()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff not found")

        updated_staff = update.model_dump(exclude_unset=True)
        update_data = {}

        # Preserve existing values
        profile_img_url = staff.profile_img
        header_img_url = staff.header_img

        # Get available avatars
        avatar_list = [
            f"/avatars/{img}" for img in os.listdir(AVATAR_DIR) if img.endswith(".svg")
        ]

        changes_detected = False  # Track if any change occurs

        # Scenario: User chooses an avatar after already having a profile image
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

        # Scenario: User uploads a new profile image (profile image takes priority over avatar)
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

        # Handle permission update (only update if changed)
        if update.permission and update.permission != staff.permission:
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

        fields_mapping = {
            "first_name": "staff_first_name",
            "last_name": "staff_last_name",
            "gender": "gender",
            "description": "description",
            "useremail":"useremail",
            "phone":"phone"
        }
        details_updates = {}

        # Loop through the fields from the update and map accordingly
        for key, value in updated_staff.items():
            if key in fields_mapping and value is not None:
                mapped_key = fields_mapping[key]
                existing_value = staff.details.get("service_provider", {}).get(
                    mapped_key
                )
                if existing_value != value:
                    details_updates[mapped_key] = value
                    changes_detected = True

        # Apply detail updates in the database
        if details_updates:
            for key, value in details_updates.items():
                db.query(models.User).filter(models.User.uuid == uuid).update(
                    {
                        "details": func.jsonb_set(
                            models.User.details,
                            f"{{service_provider,{key}}}",
                            f'"{value}"',
                            True,
                        )
                    }
                )
        if useremail:
            update_data['useremail'] = useremail
            changes_detected = True
        # Apply updates to main User fields
        if update_data:
            db.query(models.User).filter(models.User.uuid == uuid).update(update_data)

        if changes_detected:  # Commit only if any change was made
            db.commit()
            db.refresh(staff)
            logger.log_info(f"Updated fields: {update_data} and {details_updates}")
            return {"message": "Staff updated successfully", "staff": staff}

        return {"message": "No changes detected", "staff": staff}

    except Exception as e:
        logger.log_error(f"Error updating staff: {e!s}")
        raise HTTPException(status_code=500, detail=str(e))


def soft_delete_staff(
    staff_uuid: uuid.UUID,
    request: schemas.SoftDeleteRequest,
    db: Session = Depends(get_db),
):
    staff = (
        db.query(models.User)
        .filter(models.User.uuid == staff_uuid, models.User.role_type == "staff")
        .first()
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    staff.is_deleted = True
    staff.deleted_by = request.deleted_by  # Assuming the requestor's UUID is passed
    staff.deleted_at = datetime.now()

    db.commit()
    db.refresh(staff)

    return {"detail": "Staff marked as deleted successfully"}


def get_user_active_subscription(service_provider_uuid: UUID4, db: Session):
    now = datetime.now()
    membership = (
        db.query(models.Membership)
        .filter(
            models.Membership.uuid == service_provider_uuid,
            models.Membership.expiry_date >= now,
        )
        .order_by(models.Membership.billing_date.desc())
        .first()
    )

    if membership:
        subscription = (
            db.query(models.Subscription)
            .filter(models.Subscription.subscription_id == membership.subscription_id)
            .first()
        )
        return subscription
    return None


def can_rate_client(
    service_provider: models.User, client: models.User, db: Session
) -> bool:
    subscription = get_user_active_subscription(service_provider.uuid, db)

    if (
        service_provider.role_type == "service_provider"
        and client.role_type == "client"
    ):
        if "Existing Clients Only" in subscription.client_risk_reward:
            return service_provider.uuid == client.created_by

        elif "Prospective & Existing" in subscription.client_risk_reward:
            return (
                service_provider.uuid == client.created_by,
                service_provider.uuid == client.approved_by,
            )

    return False


def client_rating(rating: schemas.Rating, db: Session):
    try:
        # Validate if service provider exists
        service_provider = (
            db.query(models.User)
            .filter(models.User.uuid == rating.service_provider_uuid)
            .first()
        )
        if not service_provider:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content="Service provider not found!!!",
            )

        # Validate if client exists
        client = (
            db.query(models.User).filter(models.User.uuid == rating.client_uuid).first()
        )
        if not client:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content="Client not found"
            )

        # Compute average rating from question_answer values
        answer_values = list(rating.question_answer.values())
        numeric_values = [v for v in answer_values if isinstance(v, (int, float))]

        if not numeric_values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No numeric answers provided for rating calculation",
            )

        average_rating = sum(numeric_values) / len(numeric_values)

        # Save new rating entry
        new_rating = models.Ratings(
            client_uuid=rating.client_uuid,
            service_provider_uuid=rating.service_provider_uuid,
            question_answer=rating.question_answer,
            rated_by="service_provider",
            average_rating=average_rating,
        )

        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)

        # Fetch all ratings given to this client by service providers
        client_ratings = (
            db.query(models.Ratings.average_rating)
            .filter(
                models.Ratings.client_uuid == rating.client_uuid,
                models.Ratings.rated_by == "service_provider",
            )
            .all()
        )

        average_ratings_list = [r[0] for r in client_ratings]

        overall_avg_rating = (
            sum(average_ratings_list) / len(average_ratings_list)
            if average_ratings_list
            else 0
        )

        # Update the client's JSONB 'details' field
        details = client.details or {}
        details.setdefault("client", {})["rating"] = round(overall_avg_rating, 2)

        db.execute(
            update(models.User)
            .where(models.User.uuid == rating.client_uuid)
            .values(details=details)
        )
        db.commit()

        return {
            "message": "Rating submitted successfully",
            "average_rating": round(overall_avg_rating, 2),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred: " + str(e),
        )


def get_subscription(service_provider_uuid: UUID, db: Session):
    try:
        service_provider = (
                db.query(models.User)
                .filter(models.User.uuid == service_provider_uuid)
                .first()
            )
        titanium_obj = (
            db.query(models.Titanium)
            .filter(models.Titanium.uuid == service_provider_uuid)
            .first()
        )
        if titanium_obj:
            obj = {
                "start_date": titanium_obj.start_date,
                "expiry_date": titanium_obj.expiry_date,
                "status": titanium_obj.status,
                "service_provider_uuid": titanium_obj.uuid,
                "client_counts": titanium_obj.clients_count,
                "view_other_client": titanium_obj.view_other_client,
                "risk_reward_clients": titanium_obj.risk_reward_clients,
                "risk_reward_prospective_clients": titanium_obj.risk_reward_prospective_clients,
                "risk_reward_provider": titanium_obj.risk_reward_provider,
                "chat_restriction": titanium_obj.chat_restriction,
                "duration": titanium_obj.duration.replace("ly", ""),
                "price":titanium_obj.payment_price,
                "subscription_name": "Titanium",
                "remaining_client": titanium_obj.clients_count -service_provider.details.get("service_provider", {}).get("client_count", 0),
            }
            return {"status": 200, "data": [obj]}
        else:
            memberships = (db.query(models.Membership).filter((models.Membership.uuid == service_provider_uuid) & (models.Membership.status != "cancelled")).all())

            if not memberships:
                return {
                    "status": 200,
                    "message": "No active subscription found",
                    "data": "null",
                }

            data = []

            for membership in memberships:
                get_subscription = (
                    db.query(models.Subscription)
                    .filter(
                        models.Subscription.subscription_id
                        == membership.subscription_id
                    )
                    .first()
                )

                membership_data = {
                    "service_provider_id": str(service_provider_uuid),
                    "subscription_name": get_subscription.name,
                    "duration": membership.duration.replace("ly", ""),
                    "status": membership.status,
                    "stripe_subscription_id": membership.stripe_subscription_id,
                    "billing_date": membership.billing_date.strftime("%Y-%m-%d"),
                    "start_date": membership.start_date.strftime("%Y-%m-%d"),
                    "expiry_date": membership.expiry_date.strftime("%Y-%m-%d"),
                    "remaining_days": (membership.expiry_date - datetime.now()).days,
                    "payment_price": membership.payment_price,
                    "max_clients": get_subscription.clients_count,
                    "remaining_client": get_subscription.clients_count
                    - service_provider.details.get("service_provider", {}).get(
                        "client_count", 0
                    ),
                }
                if membership.status == "trial":
                    membership_data["payment_price"] = get_subscription.price_details.get(membership.duration, {}).get("amount", 0)
                    membership_data.update(
                        {
                            "trial_start_date": membership.trial_start_date.strftime(
                                "%Y-%m-%d"
                            ),
                            "trial_end_date": membership.trial_end_date.strftime(
                                "%Y-%m-%d"
                            ),
                            
                        }
                    )

                data.append(membership_data)

            return {"status": 200, "data": data}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error occurred: {e!s}",
        )


def get_permissions(service_provider_uuid: UUID, db: Session):
    try:
        titanium_obj = db.query(models.Titanium).filter(models.Titanium.uuid == service_provider_uuid,models.Titanium.status == "active").first()
        if titanium_obj:
            titanium_obj.subscription_id = 3
            return titanium_obj
        membership = (
            db.query(models.Membership).filter(
                and_(
                    models.Membership.uuid == service_provider_uuid,
                    or_(
                        models.Membership.status == "active",
                        models.Membership.status == "trial",
                    ),
                )
            )
        ).first()

        if not membership:
            return {"status": 200, "message": "No active subscription found"}

        return (
            db.query(models.Subscription)
            .filter(models.Subscription.subscription_id == membership.subscription_id)
            .first()
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error occurred: {e!s}",
        )


def add_subscription(
    service_provider_uuid: UUID, subscription: schemas.AddSubscription, db: Session
):
    try:
        service_provider = (
            db.query(models.User)
            .filter(models.User.uuid == service_provider_uuid)
            .first()
        )
        if not service_provider:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content="Service Provider not found",
            )

        chosen_subscription = (
            db.query(models.Subscription)
            .filter(models.Subscription.subscription_id == subscription.subscription_id)
            .first()
        )
        if not chosen_subscription:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content="Subscription not found"
            )

        price = int(chosen_subscription.price_details[subscription.duration]["amount"])

        billing_date = datetime.today()
        current_year = billing_date.year

        is_leap_year = calendar.isleap(current_year)

        if subscription.duration == "monthly":
            expiry_date = billing_date + timedelta(days=30)
        elif subscription.duration == "quarterly":
            expiry_date = billing_date + timedelta(days=90)
        else:
            expiry_date = billing_date + timedelta(days=366 if is_leap_year else 365)

        # Check if the user has an existing membership
        existing_membership = (
            db.query(models.Membership)
            .filter_by(service_provider_uuid=service_provider_uuid)
            .first()
        )

        if existing_membership and existing_membership.expiry_date <= datetime.today():
            is_trial = False
        else:
            is_trial = True if not existing_membership else existing_membership.is_trial

        new_membership = models.Membership(
            service_provider_uuid=service_provider_uuid,
            subscription_id=chosen_subscription.subscription_id,
            billing_date=billing_date,
            expiry_date=expiry_date,
            payment_method=subscription.payment_method,
            payment_intent=subscription.payment_intent,
            payment_intent_client_secret=subscription.payment_intent_client_secret,
            redirect_status=subscription.redirect_status,
            is_trial=is_trial,
            duration=subscription.duration,
            payment_price=price,
        )
        db.add(new_membership)
        db.commit()
        db.refresh(new_membership)

        if "service_provider" not in service_provider.details:
            service_provider.details["service_provider"] = {}

        service_provider.details["service_provider"]["subscription"] = {
            "subscription_id": chosen_subscription.subscription_id,
            "name": chosen_subscription.name,
            "duration": subscription.duration,
        }
        flag_modified(service_provider, "details")
        db.commit()
        db.refresh(service_provider)

        return {"message": "Subscription added successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error occurred: {e!s}",
        )


async def get_request_details(
    db: Session,
    skip: int,
    limit: int,
    provider_id: UUID | None = None,
    client_id: UUID | None = None,
    status: str | None = None,
    name: str | None = None,
):
    # if provider_id and client_id:
    #     provider = db.query(models.User).filter(models.User.uuid == provider_id).first()
    #     if not provider:
    #         raise HTTPException(status_code=404, detail="Provider not found")
    #     client = db.query(models.User).filter(models.User.uuid == client_id).first()
    #     if not client:
    #         raise HTTPException(status_code=404, detail="Client not found")

    #     query = db.query(models.Request).filter(
    #         models.Request.provider_id == provider_id,
    #         models.Request.client_id == client_id,
    #     )
    #     if status:
    #         query = query.filter(models.Request.status == status)

    #     total = query.count()
    #     results = query.offset(skip).limit(limit).all()

    #     requests_data = []
    #     for req in results:
    #         provider_name = provider.details.get("service_provider", {}).get(
    #             "name", "Unknown Provider"
    #         )
    #         requests_data.append(
    #             {
    #                 "request_id": str(req.id),  # use request_id instead of id
    #                 "client_id": str(req.client_id),
    #                 "provider_id": str(req.provider_id),
    #                 "status": req.status,
    #                 "request_details": req.request_details,
    #                 "created_at": req.created_at,
    #                 "updated_at": req.updated_at,
    #                 "organization_type":provider.details.get("organization_type", "")
    #             }
    #         )
    #     await manager.send_to_user(
    #         client_id, f"{provider_name} is {req.status} your request"
    #     )
    #     return {"total": total, "requests": requests_data}

    if provider_id:
        provider = db.query(models.User).filter(models.User.uuid == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        query = (
            db.query(models.Request, models.User)
            .join(models.User, models.Request.client_id == models.User.uuid)
            .filter(models.Request.provider_id == provider_id)
        )
        if status:
            query = query.filter(models.Request.status == status) 
        # if name:
        #     query = query.filter(
        #         or_(
        #             models.User.details['service_provider']['founder_first_name'].astext.ilike(f"%{name}%"),
        #             models.User.details['service_provider']['founder_last_name'].astext.ilike(f"%{name}%"),
        #             models.User.useremail.astext.ilike(f"%{name}%"),
        #             models.User.details['service_provider']['name'].astext.ilike(f"%{name}%"),

        #         )
        #     )

        total = query.count()
        results = query.offset(skip).limit(limit).all()

        clients_data = []
        for req, user in results:
            client_details = user.details.get("client", {}) if user.details else {}
            category_id_str = client_details.get("category_id", "")

            if isinstance(category_id_str, str):
                category_id_list = [
                    int(x) for x in category_id_str.split(",") if x.strip().isdigit()
                ]
            elif isinstance(category_id_str, list):
                category_id_list = [
                    int(x) for x in category_id_str if isinstance(x, int)
                ]
            else:
                category_id_list = []

            category_names = []
            if category_id_list:
                categories = (
                    db.query(models.Category.category_name)
                    .filter(models.Category.category_id.in_(category_id_list))
                    .all()
                )
                category_names = [category.category_name for category in categories]

            clients_data.append(
                {
                    "uuid": str(user.uuid),
                    "useremail": user.useremail,
                    "role_type": user.role_type,
                    "details": client_details,
                    "category_name": category_names,
                    "request_status": req.status,
                    "request_id": str(req.id),
                }
            )
        return {"total": total, "clients": clients_data}

    else:
        client = db.query(models.User).filter(models.User.uuid == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        if status == 'approved':
            if client.service_provider_ids is not None:
                query = db.query(models.User).filter(models.User.uuid.in_(client.service_provider_ids))
                # if name:
                #     query = query.filter(
                #         or_(
                #             models.User.details['client']['first_name'].astext.ilike(f"%{name}%"),
                #             models.User.details['client']['last_name'].astext.ilike(f"%{name}%"),
                #             models.User.useremail.astext.ilike(f"%{name}%"),
                #         )
                #     )
                total = query.count()
                results = query.offset(skip).limit(limit).all()
                for u in results:
                    print(u.details)
                providers_data = [
                {
                    "uuid": str(user.uuid),
                    "useremail": user.useremail,
                    "role_type": user.role_type,
                    "categories": user.category_id,
                    "details": user.details.get("service_provider") if user.details else None,
                    "request_status": "approved",
                }
                for user in results
            ]
            else:
                providers_data = []
                total = 0
        else:
            query = (
                db.query(models.Request, models.User)
                .join(models.User, models.Request.provider_id == models.User.uuid)
                .filter(models.Request.client_id == client_id)
                .filter(models.Request.status == status)
            )
            query = query.filter(models.Request.status == status)

            total = query.count()
            results = query.offset(skip).limit(limit).all()

            providers_data = [
                {
                    "uuid": str(user.uuid),
                    "useremail": user.useremail,
                    "role_type": user.role_type,
                    "categories":user.category_id,
                    "details": user.details.get("service_provider")
                    if user.details
                    else None,
                    "request_status": req.status,
                    "request_id": str(req.id),
                }
                for req, user in results
            ]
        return {"total": total, "providers": providers_data}


async def update_request_status(
    request_id: UUID, status_update: schemas.RequestUpdate, db: Session
):
    request = db.query(models.Request).filter(models.Request.id == request_id).first()
    provider = (
        db.query(models.User).filter(models.User.uuid == request.provider_id).first()
    )

    if provider:
        details = provider.details or {}
        if "service_provider" not in details:
            details["service_provider"] = {}

        provider_name = provider.details["service_provider"].get("name", "Unknown")
        service_provider_data = details["service_provider"]
        current_count = service_provider_data.get("client_count", 0)
        service_provider_data["client_count"] = current_count + 1
        details["service_provider"] = service_provider_data

        # Extract subscription ID
        subscription_id = service_provider_data.get("subscription")

        if isinstance(subscription_id, dict):
            subscription_id = subscription_id.get("subscription_id")

        if subscription_id:
            subscription = (
                db.query(models.Subscription)
                .filter(models.Subscription.subscription_id == subscription_id)
                .first()
            )

            if (
                subscription and isinstance(subscription.clients_count, int)
            ) or isinstance(subscription.clients_count, int):
                max_clients = subscription.clients_count
            else:
                max_clients = 0

            threshold = 0.8 * max_clients  # 80% of limit

            if current_count >= max_clients:
                await send_email(
                    provider.useremail,
                    "Alert",
                    "You have reached 100% of client limit",
                )
                raise HTTPException(
                    status_code=404, detail="You have reached 100% limit"
                )

            elif current_count + 1 >= threshold:
                await send_email(
                    provider.useremail,
                    "Alert",
                    "You have reached 80% of client limit",
                )
                provider.details = json.loads(
                    json.dumps(details)
                )  # Force update detection
                flag_modified(provider, "details")

                db.commit()
                db.refresh(provider)

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if status_update.status not in ["approved", "pending", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    # Update the request status
    request.status = status_update.status

    db.commit()
    db.refresh(request)

    # Fetch the client details
    client = db.query(models.User).filter(models.User.uuid == request.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client_details = client.details.get("client", {})
    client_first_name = client_details.get("first_name", "Unknown")
    client_last_name = client_details.get("last_name", "Unknown")

    # If the request is approved, update the client's approved_by field
    if status_update.status == "approved":
        if client.service_provider_ids is None:
            client.service_provider_ids = []
        sp_ids = list(client.service_provider_ids)
        
        if request.provider_id not in sp_ids:
            sp_ids.append(request.provider_id)
        client.service_provider_ids = sp_ids
        client.approved_by = request.provider_id
        db.commit()
        db.refresh(client)

    notification_type = None
    if status_update.status == "approved":
        notification_type = "ACCEPT_REQUEST"
    elif status_update.status == "rejected":
        notification_type = "REJECT_REQUEST"
    else:
        notification_type = "SEND_REQUEST_NOTIFY"

    if notification_type == "SEND_REQUEST_NOTIFY":
        # Assuming client model contains first_name and last_name attributes.
        user_id = request.provider_id
        message = (
            f"{client_first_name} {client_last_name} has requested to connect with you."
        )
    else:
        user_id = (
            request.client_id
        )  # Client receives notification for approval/rejection.
        message = f"Your request has been {status_update.status} by {provider_name}."

    # Create a new notification record in the database
    notification = models.Notification(
        user_id=user_id,  # Client who should receive the notification
        title="Request Status Update",
        message=message,
        is_read=False,
        type=notification_type,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    # Send real-time notification to the client via WebSocket
    await manager.send_to_user(
        request.client_id,
        {
            "type": "STATUS_UPDATE",
            "request_id": str(request.id),
            "status": request.status,
            "message": f"Your request has been {status_update.status} by {provider_name}.",
        },
    )

    return request.status


def get_service_provider_dashboard(service_provider_uuid: UUID, db: Session):
    service_provider = (
        db.query(models.User).filter(models.User.uuid == service_provider_uuid).first()
    )
    if (
        service_provider
        and service_provider.details.get("service_provider")
        and service_provider.details["service_provider"].get("subscription")
    ):
        provider_subscription_id = service_provider.details["service_provider"][
            "subscription"
        ].get("subscription_id")
    else:
        provider_subscription_id = None
    subscription = (
        db.query(models.Subscription)
        .filter(models.Subscription.subscription_id == provider_subscription_id)
        .first()
    )
    # total_staff = db.query(models.User).filter(models.User.role_type == "staff").count()
    staff_of_provider = (
        db.query(models.User)
        .filter(
            (models.User.role_type == "staff"),
            (models.User.created_by == service_provider_uuid),
        )
        .count()
    )
    total_service_provider = (
        db.query(models.User)
        .filter(
            (models.User.role_type == "service_provider"),
            (models.User.is_deleted == False),
        )
        .count()
    )
    total_client = (
        db.query(models.User)
        .filter((models.User.role_type == "client"), (models.User.is_deleted == False))
        .count()
    )
    if subscription is None:
        maximum_client = 0
    elif subscription.clients_count is not None:
        maximum_client = subscription.clients_count[0]
    else:
        maximum_client = None

    client_count = service_provider.details.get("service_provider", {}).get(
        "client_count", 0
    )
    remaining_count = maximum_client - (client_count)
    return {
        "total_staff": staff_of_provider,
        "total_service_provider": total_service_provider,
        "total_client": total_client,
        "maximum_client": maximum_client,
        "client_count": client_count,
        "remaining_count": remaining_count,
    }
