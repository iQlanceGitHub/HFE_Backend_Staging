# Existing imports
import csv
import io
import json
import os
import random
import string
import uuid
from datetime import datetime, timedelta
from fastapi.templating import Jinja2Templates
import pandas as pd
from fastapi import Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import UUID4, EmailStr
from sqlalchemy import UUID, Float, Integer, and_, cast, func, or_, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.api import schemas
from src.api.schemas import (
    ServiceProviderCreate,
)
from src.authentication import JWTtoken
from src.authentication.encryption import decrypt_password, encrypt_password, secret_key
from src.common.email_service import send_email
from src.common.translate import translate_fields
from src.configs import database
from src.configs.config import logger
from src.models import models
from src.common.tasks import redis_app
from fastapi.responses import FileResponse
get_db = database.get_db


# Get the email templates
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Server url from .env
SERVER_URL = os.getenv("SERVER_URL")


def login_info(request: schemas.Login, db: Session):
    try:
        logger.log_info(f"Login attempt for user {request.useremail}")

        login_user = (
            db.query(models.User)
            .filter(models.User.useremail == request.useremail)
            .first()
        )

        if not login_user:
            logger.log_warning(f"Invalid email attempted {request.useremail}")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "Invalid Useremail"},
            )
        if (
            login_user.role_type == "service_provider"
            or login_user.role_type == "sub_admin"
        ):
            if not login_user.is_activated:
                logger.log_warning(
                    "Deactivated account login attempt: %s", request.useremail
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "message": "Your account is currently deactivated by the admin"
                    },
                )
        if login_user.is_deleted:
            logger.log_warning(f"Deleted account login attempt {request.useremail}" )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "User not found"},
            )

        decrypted_password = decrypt_password(login_user.password, secret_key)
        if decrypted_password != request.password:
            logger.log_warning(
                f"Invalid password attempt for user {request.useremail}"
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "Invalid password"},
            )

        logger.log_info(f"User authenticated successfully {request.useremail}")
        staff_stripe_id = None
        # Fetch the role of the user who created this user
        if login_user.created_by == login_user.uuid:
            created_by_role = "self"
        elif login_user.created_by:
            creator_user = (
                db.query(models.User)
                .filter(models.User.uuid == login_user.created_by)
                .first()
            )
            staff_stripe_id = creator_user.stripe_customer_id
            created_by_role = creator_user.role_type if creator_user else None
        else:
            created_by_role = None

        # Get user details
        user_details = login_user.details or {}
        logger.log_debug("User details: %s", json.dumps(user_details, indent=4))
        

        first_name = user_details.get("first_name") or user_details.get(
            "founder_first_name", ""
        )
        last_name = user_details.get("last_name") or user_details.get(
            "founder_last_name", ""
        )
        ssn = user_details.get("ssn", "")
        gender = user_details.get("gender", "")
        address_1 = user_details.get("address_1", "")
        primary_needs = user_details.get("primary_need", None)
        city = user_details.get("city", "")

        # Extract details based on role
        if login_user.role_type == "admin":
            user_name = user_details.get("admin", {}).get("name", "")

        elif login_user.role_type == "sub_admin":
            sub_admin_details = user_details.get("sub_admin", {})
            first_name = sub_admin_details.get("first_name", "")
            last_name = sub_admin_details.get("last_name", "")
            gender = sub_admin_details.get("gender", "")
            user_name = f"{first_name} {last_name}".strip()

        elif login_user.role_type == "client":
            client_details = user_details.get("client", {})
            first_name = client_details.get("first_name", None) or ""
            last_name = client_details.get("last_name", last_name)
            ssn = client_details.get("ssn", ssn)
            gender = client_details.get("gender", gender)
            address_1 = client_details.get("address_1", address_1)
            primary_needs = client_details.get("primary_need", None)
            city = client_details.get("city", city)
            user_name = f"{first_name} {last_name}".strip()

        elif login_user.role_type == "service_provider" or "staff":
            service_provider_details = user_details.get("service_provider", {})
            user_name = service_provider_details.get("name", "")
            subscription_info = service_provider_details.get("subscription", None)
            first_name = service_provider_details.get("founder_first_name", first_name) if login_user.role_type == "service_provider" else service_provider_details.get('staff_first_name')
            last_name = service_provider_details.get("founder_last_name", last_name) if login_user.role_type == "service_provider" else service_provider_details.get('staff_last_name')
            gender = service_provider_details.get("gender", gender)
            city = service_provider_details.get("city", city)

        else:
            user_name = ""

        # Generate Token
        access_token, expiry_time = JWTtoken.create_access_token(
            data={"sub": login_user.useremail}
        )
        logger.log_info(f"Token generated successfully for user {login_user.useremail}")

        return schemas.Token(
            uuid=login_user.uuid,
            role_type=login_user.role_type,
            created_by_role=created_by_role,
            access_token=access_token,
            token_type="bearer",  # noqa: S106
            name=user_name if user_name else "",
            profile_img=login_user.profile_img,
            subscription=subscription_info
            if login_user.role_type == "service_provider"
            else None,
            first_name=first_name,
            last_name=last_name,
            ssn=ssn,
            gender=gender,
            address_1=address_1,
            primary_needs=primary_needs,
            city=city,
            created_by=login_user.created_by,
            customer_id=staff_stripe_id if staff_stripe_id else login_user.stripe_customer_id,
            expiry_time=str(expiry_time),
        )

    except Exception as e:
        logger.log_error(f"Error during login for user {request.useremail}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login",
        )


def generate_otp():
    return str(random.randint(100000, 999999))


async def forgot_password(email: str, db: Session):
    try:
        logger.log_info(f"Password reset attempt for email {email}")

        user = db.query(models.User).filter(models.User.useremail == email).first()

        if not user:
            logger.log_warning(
                f"Password reset attempt for non-existent email {email} " 
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "User not found"},
            )
            
        # Check if the user is deleted 
        if user.is_deleted:
            logger.log_warning(
                f"Password reset attempt for deleted user {email} " 
            )
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "Users is already deleted"},
            )

        # Generate a random token
        otp = generate_otp()
        logger.log_info(f"Generated OTP for email {email}")

        user.password_reset_token = otp
        user.password_reset_expires = datetime.now() + timedelta(minutes=30)

        db.commit()
        db.refresh(user)

        # HTML content to be sent
        body = f"""
        <div>
            <div
                style="margin: 50px auto; width: 60%; font-family: Inter;">
                <div
                    style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                    <a href="#" style="width:100%; text-align:center; ">
                        <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                    </a>
                </div>

                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14;">
                    Hi,
                </p>

                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                    Thank you for choosing HFE. Use the following OTP to complete your Sign Up procedures. OTP is valid for 5 minutes.
                </p>

                <h2
                    style="background: #0c2340; margin: 0 auto; width: max-content; padding: 0 10px; border-radius: 4px; font-size: 24px; font-family: Inter; font-weight: 700; color: #fff; letter-spacing: 2.5px; margin-bottom: 16px;">
                    {otp}
                </h2>

                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 500; color: #0a0d14; line-height: 20px; margin-bottom: 8px; margin-top: 30px;">
                    Regards,
                </p>
                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                    Hope For Everyday
                </p>
            </div>
        </div>
        """

        logger.log_info(f"Password reset token saved successfully for email {email} ")
        await send_email(email, "Password Reset OTP", body)

        logger.log_info(f"Password reset token sent successfully to email {email}")
        return {"message": "Password reset token sent successfully"}

    except HTTPException as e:
        logger.log_error(
            "HTTPException occurred during password reset for email %s: %s",
            email,
            str(e),
        )
        raise e
    except Exception as e:
        logger.log_error(
            "Unexpected error during password reset for email %s: %s",
            email,
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during password reset",
        )


async def verify_otp(email: str, otp: str, db: Session):
    try:
        logger.log_info(f"OTP verification attempt for email {email}")

        user = db.query(models.User).filter(models.User.useremail == email).first()

        if not user:
            key = f"otp:{email}"
            real_otp = redis_app.get(key)
            if real_otp and real_otp.strip() == otp.strip():
                redis_app.delete(key)
                logger.log_info(f"OTP verified successfully for email {email}")
                return {"message": "OTP verified successfully"}

            logger.log_warning(f"OTP not found or expired for email {email}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP not found or expired. Please request a new OTP."
            )

        if user.password_reset_token != otp:
            logger.log_warning(f"Invalid OTP attempt for email {email}" )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "Invalid OTP"},
            )

        if user.password_reset_expires < datetime.now():
            logger.log_warning(f"Expired OTP attempt for email {email}")
            return JSONResponse(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                content={"message": "OTP has expired"},
            )

        logger.log_info(f"OTP verified successfully for email {email}" )
        return {"message": "OTP verified successfully"}

    except HTTPException as e:
        logger.log_error(
            "HTTPException occurred during OTP verification for email %s: %s",
            email,
            str(e),
        )
        raise e
    except Exception as e:
        logger.log_error(
            "Unexpected error during OTP verification for email %s: %s",
            email,
            str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during OTP verification",
        )


def reset_password(OTP: str, new_password: str, db: Session = Depends(get_db)):
    try:
        logger.log_info(f"Password reset attempt using OTP {OTP}")

        user = (
            db.query(models.User)
            .filter(models.User.password_reset_token == OTP)
            .first()
        )

        if not user:
            logger.log_warning(f"Invalid OTP used for password reset {OTP}" )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"message": "Invalid OTP"},
            )

        if user.password_reset_expires < datetime.now():
            logger.log_warning(f"Expired OTP used for password reset {OTP}")
            return JSONResponse(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                content={"message": "OTP has expired"},
            )

        user.password = encrypt_password(new_password, secret_key)
        user.password_reset_token = None
        user.password_reset_expires = None

        db.commit()
        db.refresh(user)

        logger.log_info(f"Password reset successfully for user {user.useremail}")

        return {"message": "Password reset successfully"}

    except HTTPException as e:
        logger.log_error(
            f"HTTPException occurred during password reset: {str(e)}",
            
        )
        raise e
    except Exception as e:
        logger.log_error(
            f"Unexpected error during password reset: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during password reset",
        )


def generate_random_password():
    characters = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"

    # Generate a random 6-character password
    password = "".join(random.choices(characters, k=8))
    return password


async def create_service_provider(
    service_provider_original: ServiceProviderCreate, db: Session
):
    try:
        service_provider = await translate_fields(
            service_provider_original,
            fields=[
                "name",
                "service_provider_type",
                "contact_title",
                "contact_name",
                "comments",
            ],
        )

        logger.log_info(
            "Attempting to create a new service provider with email: %s",
            service_provider.email,
        )

        user = (
            db.query(models.User)
            .filter(models.User.uuid == service_provider.admin_uuid)
            .first()
        )

        useremail = (
            db.query(models.User)
            .filter(
                models.User.useremail == service_provider.email,
                models.User.is_deleted == False,
            )
            .first()
        )
        if useremail:
            logger.log_warning(
                f"Service Provider already exists with email {service_provider.email}"
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"message": "Email ID already exists."},
            )

        if not user or not user.is_activated:
            logger.log_warning(
                f"Deactivated user attempted to create service provider {service_provider.email}"
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "message": "You are deactivated. Cannot create service provider"
                },
            )

        generated_password = generate_random_password()
        encrypted_password = encrypt_password(generated_password, secret_key)

        existing_user = (
            db.query(models.User)
            .filter(models.User.useremail == service_provider.email)
            .first()
        )

        if existing_user:
            logger.log_warning(
                f"Duplicate email or Tax ID detected: {service_provider.email}"
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content="Tax ID or Email already exists",
            )

        new_user = models.User(
            created_by=service_provider.admin_uuid,
            useremail=service_provider.email,
            password=encrypted_password,
            details={
                "service_provider": {
                    "name": service_provider.name,
                    "contact_title": service_provider.contact_title,
                    "contact_name": service_provider.contact_name,
                    "phone": service_provider.phone,
                    "email": service_provider.email,
                    "website_link": service_provider.website_link,
                    "description": service_provider.description,
                    "organization_type": service_provider.organization_type,
                }
            },
            role_type="service_provider",
            is_activated=True,
            status="verified",
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.log_info(
            f"Service Provider created successfully with email: {service_provider.email}"
            ,
        )

        body = f"""
                <div>
            <div
                style="margin: 50px auto; width: 60%; font-family: Inter;">
                <div
                    style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                    <a href="#" style="width:100%; text-align:center; ">
                        <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                    </a>
                </div>

                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14;">
                    Hi {service_provider.name},
                </p>

                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                   Welcome to the Hope For Everybody (HFE) Admin Portal!
                    Your account has been successfully created by our Super Admin team.
                    Here are your login credentials:
                </p>
                <p>Here are your login credentials:</p>
                <ul>
                    <li><strong>Email:</strong>{service_provider.email}</li>
                     <li><strong>Password:</strong>{generated_password}</li>
                </ul>
                <p>
                    <strong>Important:</strong>
                    For your security, please log in and update your password after your first login.
                    You can access the Admin Portal here: [Login Link]
                    If you encounter any issues or have questions about your role, feel free to reach out to the support team.
                    We’re excited to have you onboard!
                </p>
                <p
                    style="font-size: 16px; font-family: Inter; font-weight: 500; color: #0a0d14; line-height: 20px; margin-bottom: 8px; margin-top: 30px;">
                    Thank you,
                </p>
                <p><strong>The HFE Admin Team</strong></p>
                <a href="link">Link</a>
            </div>
        </div>
        """
        await send_email(
            service_provider.email,
            "You are created as a Service Provider by Admin",
            body,
        )

        logger.log_info(
            "Login credentials sent successfully to: %s", service_provider.email
        )

        return schemas.ServiceProviderResponse(
            uuid=new_user.uuid,
            created_by=service_provider.admin_uuid,
        )
    except HTTPException as e:
        logger.log_error(
            "HTTPException occurred during service provider creation: %s",
            str(e),
        )
        raise e
    except Exception as e:
        db.rollback()
        logger.log_error(
            "Unexpected error during service provider creation: %s",
            str(e),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=str(e)
        )


async def get_all_service_providers(
    skip: int,
    limit: int,
    db: Session,
    name_original: str = None,
    client_uuid: str = None,
    favourite: bool = None,
    blocked: bool = None,
    estimated_clients: int = None,
    organization_type_original: str = None,
    country_original: str = None,
    city_original: str = None,
    zipcode: int = None,
    category: int = None,
    sub_category: int = None,
    status: str = None,
    is_activated: bool = None,
    sort_by: str = None,
    sort_order: str = "asc",
    old_new: str = None,
    primary_need: int = None,
    secondary_need: str = None,
    role_type: str = None,
    region:str = None,
):
    try:
        name = await translate_fields(name_original, fields=[])
        organization_type = await translate_fields(
            organization_type_original, fields=[]
        )
        county = await translate_fields(country_original, fields=[])
        city = await translate_fields(city_original, fields=[])

        query = db.query(models.User).filter(
            models.User.role_type == "service_provider", models.User.is_deleted == False
        )

        if is_activated is not None:
            query = query.filter(models.User.is_activated == is_activated)

        if status:
            query = query.filter(models.User.status == status)

        if name:
            query = query.filter(
                models.User.useremail.ilike(f"%{name}%")
                |
                models.User.details["service_provider"]["name"].astext.ilike(
                    f"%{name}%"
                )
                | models.User.details["service_provider"]["phone"].astext.ilike(
                    f"%{name}%"
                )
                | models.User.details["service_provider"]["city"].astext.ilike(f"%{name}%")
                | models.User.details["service_provider"]["contact_name"].astext.ilike(
                    f"%{name}%"
                )
                | models.User.details["service_provider"]["contact_email"].astext.ilike(
                    f"%{name}%"
                )
                | models.User.details["service_provider"][
                    "founder_first_name"
                ].astext.ilike(f"%{name}%")
                | models.User.details["service_provider"][
                    "founder_last_name"
                ].astext.ilike(f"%{name}%")
                | models.User.useremail.ilike(f"%{name}%")
                | models.User.details["service_provider"][
                    "keywords"
                ].astext.ilike(f"%{name}%")
            )

        if estimated_clients:
            query = query.filter(
                models.User.details["service_provider"][
                    "estimated_clients"
                ].astext.ilike(f"{estimated_clients}")
            )

        if organization_type:
            query = query.filter(
                models.User.details["service_provider"][
                    "organization_type"
                ].astext.ilike(f"{organization_type}%")
            )

        if county:
            query = query.filter(
                models.User.details["service_provider"]["county"].astext.ilike(
                    f"%{county}%"
                )
            )

        if city:
            query = query.filter(
                models.User.details["service_provider"]["city"].astext.in_([city.upper()])
            )
        if zipcode:
            query = query.filter(
                models.User.details["service_provider"]["zip_code"].astext.ilike(
                    f"{zipcode}"
                )
            )

        if category:
            query = query.filter(
                models.User.details["service_provider"]["category_id"].astext.ilike(
                    f"%{category}%"
                )
            )

        if sub_category:
            query = query.filter(
                models.User.details["service_provider"]["sub_category_id"].astext.ilike(
                    f"%{sub_category}%"
                )
            )
        if region:
            query = query.filter(
                models.User.details["service_provider"]["region"].astext.ilike(
                    f"%{region}%"
                )
            )


        if blocked and client_uuid:
            subquery = (
                db.query(models.FavouriteBlocked.blocked_to)
                .filter(models.FavouriteBlocked.blocked_by == client_uuid)
                .subquery()
            )

            query = query.filter(models.User.uuid.in_(subquery))

        if favourite and client_uuid:
            subquery = (
                db.query(models.FavouriteBlocked.favourited_to)
                .filter(models.FavouriteBlocked.favourited_by == client_uuid)
                .subquery()
            )

            query = query.filter(models.User.uuid.in_(subquery))

        if sort_by:
            if sort_by in [
                "name",
                "email",
                "created_at",
                "status",
            ]:
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
        if role_type == 'admin':
            query = query.order_by(models.User.created_at.desc())

        if old_new:
            filter_date = datetime.now() - timedelta(days=30)
            if old_new.lower() == "new":
                query = query.filter(models.User.created_at >= filter_date)
            elif old_new.lower() == "old":
                query = query.filter(models.User.created_at < filter_date)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid value for old_new. Use 'new' or 'old'.",
                )
        
        conditions = []

        if primary_need is not None:
            primary_condition = text(
                "category_id->'category' @> :primary_match"
            ).bindparams(primary_match=f'[{{"id": {int(primary_need)}, "status": "approved"}}]')
            conditions.append(primary_condition)

        if secondary_need:
            try:
                secondary_need_list = [
                    int(x.strip())
                    for x in secondary_need.split(",")
                    if x.strip().isdigit()
                ]
            except Exception:
                raise HTTPException(
                    status_code=400, detail="Invalid format for secondary_need"
                )

            for index, id in enumerate(secondary_need_list):
                param_name = f"secondary_match_{index}"
                condition = text(
                    f"category_id->'category' @> :{param_name}"
                ).bindparams(**{param_name: f'[{{"id": {id}, "status": "approved"}}]'})
                conditions.append(condition)

        if conditions:
            query = query.filter(or_(*conditions))
        result_query = query.offset(skip).limit(limit)
        service_providers = result_query.all()
        # print("query to excute",result_query.statement.compile(compile_kwargs={"literal_binds": True}))
        
        total_service_provider = query.count()
        formatted_providers = []
        for service_provider in service_providers:
            estimated_clients = service_provider.details.get(
                "service_provider", {}
            ).get("estimated_clients", None)
            try:
                estimated_clients = (
                    int(estimated_clients) if estimated_clients is not None else 0
                )
            except ValueError:
                estimated_clients = 0

            socialmedia_links = service_provider.details.get(
                "service_provider", {}
            ).get("socialmedia_links", None)
            if isinstance(socialmedia_links, str) and socialmedia_links:
                socialmedia_links = socialmedia_links.split(',')

            keywords = service_provider.details.get("service_provider", {}).get("keywords", [])
            if isinstance(keywords, str) and keywords:
                try:
                    keywords = json.loads(keywords)
                except json.JSONDecodeError:
                    keywords = [keyword.strip() for keyword in keywords.split(",") if keyword.strip()]
            elif not keywords:
                keywords = []

            category_id = service_provider.details.get("service_provider", {}).get(
                "category_id", ""
            )
            sub_category_id = service_provider.details.get("service_provider", {}).get(
                "sub_category_id", ""
            )

            category_name = None
            sub_category_name = None

            if category_id:
                category = (
                    db.query(models.Category.category_name)
                    .filter(models.Category.category_id == category_id)
                    .first()
                )
                category_name = category.category_name if category else None

            if sub_category_id:
                sub_category = (
                    db.query(models.SubCategory.sub_category_name)
                    .filter(models.SubCategory.sub_category_id == sub_category_id)
                    .first()
                )
                sub_category_name = (
                    sub_category.sub_category_name if sub_category else None
                )
            subscriptions = []
            get_titanium = db.query(models.Titanium).filter(
                (models.Titanium.uuid == service_provider.uuid) & 
                (models.Titanium.status == "active")
            ).first()
            
            if get_titanium:
                subscriptions.append({"subscription_name":"Titanium","status":get_titanium.status})
            else:
                get_subscriptions = db.query(models.Membership).filter(
                    models.Membership.uuid == service_provider.uuid,
                    models.Membership.status.in_(["active", "trial", "upcoming"])
                ).all()
                if get_subscriptions:
                    for subscription in get_subscriptions:
                        get_subscription = (
                            db.query(models.Subscription)
                            .filter(models.Subscription.subscription_id == subscription.subscription_id)
                            .first()
                        )
                        subscriptions.append({"subscription_name": get_subscription.name,"status": subscription.status})

            formatted_providers.append(
                {
                    "uuid": str(service_provider.uuid),
                    "name": service_provider.details.get("service_provider", {}).get(
                        "name", ""
                    ),
                    "phone": service_provider.details.get("service_provider", {}).get(
                        "phone", ""
                    ),
                    "estimated_clients": estimated_clients,
                    "tax_id": service_provider.details.get("service_provider", {}).get(
                        "tax_id", ""
                    ),
                    "organization_type": service_provider.details.get(
                        "service_provider", {}
                    ).get("organization_type", ""),
                    "contact_title": service_provider.details.get(
                        "service_provider", {}
                    ).get("contact_title", ""),
                    "contact_email": service_provider.details.get("service_provider", {}).get("contact_email", ""),
                    "contact_name": service_provider.details.get(
                        "service_provider", {}
                    ).get("contact_name", ""),
                    "email": service_provider.useremail,
                    "founder_first_name": service_provider.details.get(
                        "service_provider", {}
                    ).get("founder_first_name", ""),
                    "founder_last_name": service_provider.details.get(
                        "service_provider", {}
                    ).get("founder_last_name", ""),
                    "address_1": service_provider.details.get(
                        "service_provider", {}
                    ).get("address_1", ""),
                    "address_2": service_provider.details.get(
                        "service_provider", {}
                    ).get("address_2", ""),
                    "country": service_provider.details.get("service_provider", {}).get(
                        "country", ""
                    ),
                    "city": service_provider.details.get("service_provider", {}).get(
                        "city", ""
                    ),
                    "region": service_provider.details.get("service_provider", {}).get(
                        "region", ""
                    ),
                    "state": service_provider.details.get("service_provider", {}).get("state", ""),
                    "lat": service_provider.details.get("service_provider", {}).get(
                        "lat", ""
                    ),
                    "long": service_provider.details.get("service_provider", {}).get(
                        "long", ""
                    ),
                    "zip_code": service_provider.details.get(
                        "service_provider", {}
                    ).get("zip_code", ""),
                    "website_link": service_provider.details.get(
                        "service_provider", {}
                    ).get("website_link", ""),
                    "comments": service_provider.details.get(
                        "service_provider", {}
                    ).get("comments", ""),
                    "rating": service_provider.details.get("service_provider", {}).get(
                        "rating", ""
                    ),
                    "brochure": service_provider.details.get(
                        "service_provider", {}
                    ).get("brochure", ""),
                    "description": service_provider.details.get(
                        "service_provider", {}
                    ).get("description", ""),
                    "county": service_provider.details.get("service_provider", {}).get(
                        "county", ""
                    ),
                    "question": service_provider.details.get(
                        "service_provider", {}
                    ).get("question", ""),
                    "socialmedia_links": socialmedia_links,
                    "profile_img": service_provider.profile_img,
                    "header_img": service_provider.header_img,
                    "client_count": service_provider.details.get(
                        "service_provider", {}
                    ).get("client_count", ""),
                    "category": category_name,
                    "sub_category": sub_category_name,
                    "service_provider_type": service_provider.service_provider_type,
                    "is_activated": service_provider.is_activated,
                    "status": service_provider.status,
                    "created_at": service_provider.created_at,
                    "subscription": subscriptions,
                    "categories":service_provider.category_id,
                    "keywords": keywords
                }
            )

        return {
            "total_service_provider": total_service_provider,
            "service_provider": formatted_providers,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"message": f"An error occurred: {e!s}"}
        )


def get_service_provider(uuid: UUID, db: Session):
    try:
        service_provider = (
            db.query(models.User).filter(models.User.uuid == uuid).first()
        )
        name = service_provider.details.get("service_provider", {}).get("name")
        if not service_provider:
            return JSONResponse(
                status_code=404, content={"message": "No service provider found"}
            )

        role_type = (
            db.query(models.User.role_type)
            .filter(models.User.uuid == service_provider.created_by)
            .first()
        )
        if service_provider.created_by == service_provider.uuid:
            role_type_value = "self"
            name_value = None

        else:
            role_type_value = role_type[0] if role_type else None
            name_value = name

        if service_provider.is_deleted:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "message": "Requested Service provider is no longer available"
                },
            )

        details = service_provider.details.get("service_provider", {})
        estimated_clients = service_provider.details.get("service_provider", {}).get(
            "estimated_clients", None
        )
        try:
            estimated_clients = (
                int(estimated_clients) if estimated_clients is not None else 0
            )
        except ValueError:
            estimated_clients = 0

        category_id = details.get("category_id", None)
        sub_category_id = details.get("sub_category_id", None)

        category_name = None
        sub_category_name = None

        if category_id:
            category = (
                db.query(models.Category.category_name)
                .filter(models.Category.category_id == category_id)
                .first()
            )
            category_name = category.category_name if category else None

        if sub_category_id:
            sub_category = (
                db.query(models.SubCategory.sub_category_name)
                .filter(models.SubCategory.sub_category_id == sub_category_id)
                .first()
            )
            sub_category_name = sub_category.sub_category_name if sub_category else None
        titanium_obj = db.query(models.Titanium).filter((models.Titanium.uuid == uuid) & (models.Titanium.status == "active")).first()
        subcriptions = []
        if titanium_obj:
            subcriptions.append({
                "subscription_name":"Titanium",
                "clients_count": titanium_obj.clients_count,
                "chat_restriction" :titanium_obj.chat_restriction,
                "view_other_client" :titanium_obj.view_other_client,
                "risk_reward_clients" :titanium_obj.risk_reward_clients,
                "risk_reward_prospective_clients" : titanium_obj.risk_reward_prospective_clients,
                "risk_reward_provider" : titanium_obj.risk_reward_provider,
                "duration" : titanium_obj.duration,
                "price":titanium_obj.payment_price
                
            })
        else:
            get_subscriptions = db.query(models.Membership).filter(
                models.Membership.uuid == service_provider.uuid,
                models.Membership.status.in_(["active", "trial", "upcoming"])
            ).all()
            if get_subscriptions:
                for subscription in get_subscriptions:
                    get_subscription = (
                        db.query(models.Subscription)
                        .filter(models.Subscription.subscription_id == subscription.subscription_id)
                        .first()
                    )
                    subcriptions.append({"subscription_name": get_subscription.name,"status": subscription.status})
        links = []
        if details.get("socialmedia_links", ""):
            if  isinstance(details.get("socialmedia_links"), str):
                links = details.get("socialmedia_links", "").split(",")
            
                
        return {
            "uuid": str(service_provider.uuid),
            "name": details.get("name", ""),
            "phone": details.get("phone", ""),
            "isTitanium": service_provider.is_titanium_requested,
            "estimated_clients": estimated_clients,
            "role_type": str(service_provider.role_type),
            "tax_id": details.get("tax_id", ""),
            "contact_title": details.get("contact_title", ""),
            "contact_name": details.get("contact_name", ""),
            "contact_email": details.get("contact_email", ""),
            "email": details.get("email", ""),
            "organization_type": details.get("organization_type", ""),
            # "founder_name": f"{details.get('founder_first_name', '')} {details.get('founder_last_name', '')}".strip(),
            "founder_first_name": details.get("founder_first_name", ""),
            "founder_last_name": details.get("founder_last_name", ""),
            "address_1": details.get("address_1", ""),
            "address_2": details.get("address_2", ""),
            "country": details.get("country", ""),
            "city": details.get("city", ""),
            "region": details.get("region", ""),
            "lat": details.get("lat", ""),
            "long": details.get("long", ""),
            "state": details.get("state", ""),
            "category_id": details.get("category_id", ""),
            "category_name": category_name,
            "sub_category_id": details.get("sub_category_id", ""),
            "sub_category_name": sub_category_name,
            "zip_code": details.get("zip_code", ""),
            "socialmedia_links": links if len(links) > 0 else details.get("socialmedia_links", []),
            "service_provider_type": service_provider.service_provider_type,
            "question": details.get("question", ""),
            "website_link": details.get("website_link", ""),
            "comments": details.get("comments", ""),
            "brochure": details.get("brochure", ""),
            "description": details.get("description", ""),
            "county": details.get("county", ""),
            # "password": decrypted_password,
            "is_activated": service_provider.is_activated,
            "status": service_provider.status,
            "created_by_role_type": role_type_value,
            "created_by_name": name_value,
            "created_at": service_provider.created_at,
            "updated_at": service_provider.updated_at,
            "is_deleted": service_provider.is_deleted,
            "deleted_by": service_provider.deleted_by,
            "deleted_at": service_provider.deleted_at,
            "subscription": subcriptions,
            "rating": details.get("rating", ""),
            "profile_img": service_provider.profile_img,
            "header_img": service_provider.header_img,
            "client_count": details.get("client_count", ""),
            "categories":service_provider.category_id,
            "keywords":details.get("keywords", [])
        }
    except HTTPException as e:
        raise e

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": "Internal Server Error", "details": str(e)},
        )


async def update_provider_status(
    service_provider_uuid: UUID, status_update: schemas.StatusUpdate, db: Session
):
    try:
        logger.log_info(
            f"Attempting to update status for service provider UUID {service_provider_uuid}",
            
        )

        provider = (
            db.query(models.User)
            .filter(models.User.uuid == service_provider_uuid)
            .first()
        )
        if not provider:
            logger.log_warning(f"Service provider not found {service_provider_uuid}" )
            raise HTTPException(status_code=404, detail="Provider not found")

        if status_update.status not in ["verified", "pending", "refuted"]:
            logger.log_warning(
                f"Invalid status update attempt {status_update.status}")
            raise HTTPException(status_code=400, detail="Invalid status")

        if provider.status == status_update.status:
            logger.log_warning(
                f"Provider is already {status_update.status}")
            return JSONResponse(status_code=400, content={"message": f"Provider is already {status_update.status}"})
        provider.status = status_update.status
        provider.is_activated = True if status_update.status == "verified" else False
        
        name = provider.details.get("service_provider").get("name") 
        if status_update.status == "refuted" and status_update.refuted_message:
            
            logger.log_info(
                "Sending refuted message email to provider: %s", provider.useremail
            )
            
            body = f"""
                    <div>
                        <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                            <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                                <a href="#" style="width:100%; text-align:center;">
                                    <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                                </a>
                            </div>
                    
                            <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14;">
                                Hi {name if name else ""},
                            </p>
                    
                            <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                We regret to inform you that your account verification request has been reviewed and unfortunately refuted by our Super Admin team.
                                <br /><br />
                                <strong>Reason for Refusal:</strong>
                                <p>
                                    {status_update.refuted_message}
                                </p>
                                <br /><br />
                                If you have any questions or would like clarification, feel free to reach out to us. We encourage you to review the feedback and consider reapplying if applicable.
                            </p>
                    
                            <p style="font-size: 16px; font-family: Inter; font-weight: 500; color: #0a0d14; line-height: 20px; margin-bottom: 8px; margin-top: 30px;">
                                Thank you for your understanding.
                            </p>
                            <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                The HFE Team
                            </p>
                    
                            <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px; margin-top: 30px;">
                                For any inquiries or support, feel free to reach out to us at: <a href="mailto:{os.getenv("SUPPORT_EMAIL")}">Support Email</a>
                            </p>
                    
                            <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                Visit our website: <a href="{os.getenv("BASE_URL")}">HFE</a>
                            </p>
                        </div>
                    </div>
                    """
            await send_email(provider.useremail, "You are refuted by the Admin", body)

        if status_update.status == "verified" and status_update.refuted_message:
            logger.log_info(
                f"Sending verified message email to provider {provider.useremail}"
            )
            body = f"""
        <div>
            <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                    <a href="#" style="width:100%; text-align:center;">
                        <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                    </a>
                </div>
        
                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14;">
                    Hi {name if name else ""},
                </p>
        
                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                    We are pleased to inform you that your account has been successfully verified by the Super Admin team on the Hope For Everybody (HFE) platform.
                    <br /><br />
                    Here are your login details:
                    <div>
                        <strong>Email:</strong>{provider.useremail}<br />
                        <strong>Password:</strong> {provider.password}
                    </div>
                </p>
                <p style="font-size: 16px; font-family: Inter; font-weight: 500; color: #0a0d14; line-height: 20px; margin-bottom: 8px; margin-top: 30px;">
                    If you have any questions or need assistance, please don’t hesitate to contact our support team.
                </p>
        
                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                    Thank you,
                </p>
                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                    The HFE Team
                </p>
        
                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px; margin-top: 30px;">
                    For any inquiries or support, feel free to reach out to us at: <a href="mailto:{os.getenv("SUPPORT_EMAIL")}">Support Email</a>
                </p>
        
                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                    Visit our website: <a href="{os.getenv("BASE_URL")}">HFE</a>
                </p>
            </div>
        </div>

"""
            await send_email(provider.useremail, "You are verified by the Admin", body)

        db.commit()
        db.refresh(provider)

        logger.log_info(
            f"Successfully updated status for service provider UUID {service_provider_uuid} to { provider.status}"
    
           
        )

        return f"The status of the service provider with UUID {service_provider_uuid} has been updated to '{provider.status}'."

    except HTTPException as e:
        logger.log_error(
            "HTTPException occurred while updating provider status: %s",
            str(e),
        )
        raise e
    except Exception as e:
        logger.log_error(
            "Unexpected error while updating provider status: %s",
            str(e),
        )
        raise HTTPException(
            status_code=500, detail=f"An error occurred while updating provider status:{e}"
        )


async def update_service_provider(
    uuid: UUID,
    request: Request,
    updated_service_provider_original: schemas.AdminUpdateServiceProvider,
    brochure: UploadFile | str | None = File(None),
    db: Session = Depends(get_db),
):
    try:
        updated_service_provider = await translate_fields(
            updated_service_provider_original,
            fields=[
                "name",
                "service_provider_type",
                "contact_title",
                "contact_name",
                "comments",
            ],
        )

        update_data = {"useremail": updated_service_provider_original.email}
        if update_data:
            db.query(models.User).filter(models.User.uuid == uuid).update(update_data)
        
        logger.log_info(f"Starting update for service provider with UUID: {uuid}")

        service_provider = (
            db.query(models.User).filter(models.User.uuid == uuid).first()
        )
        if not service_provider:
            logger.log_warning(f"Service provider not found for UUID: {uuid}")
            return JSONResponse(
                status_code=404, content={"message": "Service provider not found"}
            )
        service_provider.updated_by = updated_service_provider.admin_uuid
        if updated_service_provider.categories:
            categories = json.loads(updated_service_provider.categories)
            service_provider.category_id = categories
            logger.log_info(f"Updating categories to {categories}")
        
        if brochure is None:
            service_provider.brochure = None
        elif brochure is not None:
            brochure_url = save_uploaded_pdf(brochure, request, folder="brochure", mount="brochure")
            if brochure_url:
                service_provider.brochure = brochure_url

        if updated_service_provider:
            for key, value in updated_service_provider.model_dump().items():
                if value is not None and value != "":
                    if key == "socialmedia_links":
                        value = ",".join(value)
                    if key == "categories":
                        continue
                    logger.log_info(
                        f"Updating field '{key}' to '{value}'"
                    )
                    db.query(models.User).filter(models.User.uuid == uuid).update(
                    {
                        "details": func.jsonb_set(
                            models.User.details,
                            f"{{service_provider,{key}}}",
                            f'"{value}"',
                        )
                    }
                )
                    
        db.commit()
        db.refresh(service_provider)

        logger.log_info(f"Successfully updated service provider {uuid}")
        return {
            "service_provider_uuid": service_provider.uuid,
            "updated_at": datetime.now(),
            "updated_by": updated_service_provider.admin_uuid,
        }
    except HTTPException as e:
        logger.log_error(f"HTTPException occurred: {e!s}")
        raise e
    except Exception:
        logger.log_error("Unexpected error occurred during service provider update")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def status_service_provider(service_provider_uuid: UUID, db: Session):
    try:
        logger.log_info(f"Fetching service provider with UUID: {service_provider_uuid}")

        del_service_provider = (
            db.query(models.User)
            .filter(models.User.uuid == service_provider_uuid)
            .first()
        )

        if del_service_provider is None:
            logger.log_warning(
                f"Service Provider not found for UUID: {service_provider_uuid}"
            )
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Service Provider not found"
            )

        del_service_provider.is_activated = not del_service_provider.is_activated
        # del_service_provider.status = "verified" if del_service_provider.is_activated else "pending"
        del_service_provider.updated_at = datetime.now()
        del_service_provider.activated_at = datetime.now()
        db.commit()

        logger.log_info(
            f"Service Provider {service_provider_uuid} status changed to {del_service_provider.is_activated}"
        )
        password = decrypt_password(del_service_provider.password, secret_key)
        body = templates.get_template("activated.html").render(
            name = del_service_provider.details.get("service_provider").get("contact_name"),
            useremail = del_service_provider.useremail,
            password = password,
            support_email = os.getenv("SUPPORT_EMAIL"),
            website_link = os.getenv("WEBSITE_URL")
        )
        await send_email(
             del_service_provider.useremail,
             "Welcome! Your Account Has Been Activated",
             body
        )

        return {
            "detail": "Service Provider status changed successfully",
            "is_activated": del_service_provider.is_activated,
        }

    except HTTPException as e:
        logger.log_error(f"HTTPException occurred: {e!s}")
        raise e
    except Exception:
        logger.exception(
            "Unexpected error occurred while changing service provider status"
        )
        raise HTTPException(status_code=500, detail="Internal Server Error")


def delete_service_provider(
    uuid: UUID, admin_uuid: schemas.SoftDeleteServiceProvider, db: Session
):
    try:
        logger.log_info(f"Attempting to delete service provider with UUID: {uuid}")

        del_service_provider = (
            db.query(models.User).filter(models.User.uuid == uuid).first()
        )

        if not del_service_provider:
            logger.log_warning(f"No service provider found for UUID: {uuid}")
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "No service provider found"},
            )

        if del_service_provider.is_deleted:
            logger.log_warning(f"Service provider with UUID: {uuid} is already deleted")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"message": "Service provider is already deleted"},
            )

        del_service_provider.is_deleted = True
        del_service_provider.is_activated = False
        del_service_provider.deleted_by = admin_uuid.deleted_by
        del_service_provider.deleted_at = datetime.now()

        db.commit()
        logger.log_info(
            f"Service provider {uuid} successfully deleted by {admin_uuid.deleted_by}"
        )

        return {
            "deleted_by": admin_uuid.deleted_by,
            "details": "Service Provider deleted successfully",
        }
    except HTTPException as e:
        logger.log_error(f"HTTPException occurred: {e!s}")
        raise e
    except Exception:
        logger.exception("Unexpected error occurred while deleting service provider")
        raise HTTPException(status_code=500, detail="Internal Server Error")


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AVATAR_FOLDER = os.path.join(BASE_DIR, "avatars")
IMAGE_DIR = os.path.join(BASE_DIR, "hfe_images")
AVATAR_DIR = os.path.join(BASE_DIR, "avatars")
BROCHURE = os.path.join(BASE_DIR, "brochure")


def get_avatars():
    try:
        logger.log_info(f"Fetching avatars from directory")
        avatars = [
            f"/avatars/{file}"
            for file in os.listdir(AVATAR_FOLDER)
            if os.path.isfile(os.path.join(AVATAR_FOLDER, file))
        ]
        return {"avatars": avatars}
    except Exception as e:
        logger.log_error(f"Error fetching avatars: {e}")
        return {"error": str(e)}


os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(AVATAR_DIR, exist_ok=True)
os.makedirs(BROCHURE, exist_ok=True)


def save_uploaded_file(
    file: UploadFile, request: Request, folder: str | None = None
) -> str | None:
    if not file:
        logger.log_warning(f"No file provided for upload")
        return None

    folder = folder or IMAGE_DIR
    file_uuid = str(uuid.uuid4())
    _, ext = os.path.splitext(file.filename)
    new_filename = f"{file_uuid}_{file.filename}"
    file_path = os.path.join(folder, new_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        base_url = str(request.base_url).rstrip("/")
        logger.log_info(f"File saved successfully: {file_path}")
        return f"{base_url}/api/images/{new_filename}"
    except Exception as e:
        logger.log_error(f"Error saving file: {e}")
        return None


def save_uploaded_pdf(
    file: UploadFile | str,
    request: Request,
    folder: str | None = None,
    mount: str | None = None,
) -> str | None:
    if not file:
        logger.log_warning(f"No file provided for PDF upload")
        return None

    if isinstance(file, str):
        return file

    folder = folder or IMAGE_DIR
    mount = mount or "pdfs"

    file_uuid = str(uuid.uuid4())
    new_filename = f"{file_uuid}_{file.filename}"
    file_path = os.path.join(folder, new_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        base_url = str(request.base_url).rstrip("/")
        logger.log_info(f"PDF file saved successfully: {file_path}")
        return f"{base_url}/api/{mount}/{new_filename}"
    except Exception as e:
        logger.log_error(f"Error saving PDF file: {e}")
        return None


async def create_client(
    request: Request,
    client_original: schemas.ClientCreate,
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    avatar_selection: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        client = await translate_fields(
            client_original,
            fields=[
                "first_name",
                "last_name",
                "gender",
                "address_1",
                "address_2",
                "city",
                "county",
                "state",
            ],
        )

        logger.log_info(f"Creating client with email: {client.useremail}")

        user = (
            db.query(models.User).filter(models.User.uuid == client.admin_uuid).first()
        )
        if not user or not user.is_activated:
            logger.log_warning("User is deactivated, cannot create client")
            return JSONResponse(
                status_code=403,
                content={"message": "You are deactivated. Cannot create client"},
            )

        existing_client = (
            db.query(models.User)
            .filter(
                models.User.useremail == client.useremail,
                models.User.is_deleted.is_(False),
            )
            .first()
        )
        if existing_client:
            logger.log_warning("Client already exists")
            return JSONResponse(
                status_code=409, content={"message": "Client already exists"}
            )

        profile_img_url = (
            save_uploaded_file(profile_img, request) if profile_img else None
        )
        header_img_url = save_uploaded_file(header_img, request) if header_img else None

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

        # Generate and hash password
        generated_password = generate_random_password()
        password = encrypt_password(generated_password, secret_key)
        logger.log_info(f"Generated password for new client")

        # Create new client in the database
        new_client = models.User(
            created_by=client.admin_uuid,
            useremail=client.useremail,
            password=password,
            role_type="client",
            profile_img=profile_img_url,
            header_img=header_img_url,
            is_activated=True,
            service_provider_ids=[client.admin_uuid],
            status="verified",
            details={
                "client": {
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "dob": client.dob,
                    "ssn": client.ssn,
                    "gender": client.gender,
                    "address_1": client.address_1,
                    "address_2": client.address_2,
                    "city": client.city,
                    "county": client.county,
                    "state": client.state,
                    "zip_code": client.zip_code,
                    "region": client.region,
                    "lat": client.lat,
                    "long": client.long,
                    "phone": client.phone,
                    "email": client.useremail,
                    "website_link": client.website_link,
                    "profile_img": profile_img_url,
                    "header_image": header_img_url,
                }
            },
        )

        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        logger.log_info(f"New client created successfully with UUID: {new_client.uuid}")

        service_provider = (
            db.query(models.User).filter(models.User.uuid == client.admin_uuid).first()
        )

        if service_provider.role_type == "service_provider":
            details = service_provider.details or {}
            if "service_provider" not in details:
                details["service_provider"] = {}

            service_provider_data = details["service_provider"]
            current_count = service_provider_data.get("client_count", 0)
            service_provider_data["client_count"] = current_count + 1
            details["service_provider"] = service_provider_data

            # Extract subscription ID and validate it
            subscription_id = service_provider_data.get("subscription")

            if isinstance(subscription_id, dict):
                subscription_id = subscription_id.get("subscription_id")

            if subscription_id:
                subscription = (
                    db.query(models.Subscription)
                    .filter(models.Subscription.subscription_id == subscription_id)
                    .first()
                )

                if subscription is not None and subscription.clients_count is not None:
                    if isinstance(subscription.clients_count, list):
                        if len(subscription.clients_count) >= 2:
                            max_clients = subscription.clients_count[
                                1
                            ]  # Get the max allowed clients
                        elif len(subscription.clients_count) == 1:
                            max_clients = subscription.clients_count[0]
                        else:
                            max_clients = 0
                elif isinstance(subscription.clients_count, int):
                    max_clients = subscription.clients_count
                else:
                    max_clients = 0

                threshold = 0.8 * max_clients  # 80% of limit

                if current_count + 1 >= threshold:
                    name = service_provider.details.get("service_provider")
                    body = f"""
                    <div>
                            <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                                <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                                    <a href="#" style="width:100%; text-align:center;">
                                        <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                                    </a>
                                </div>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14;">
                                    Hi {name["name"] if name["name"] else ""},
                                </p>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                    We wanted to give you a heads-up that you’ve currently used 80% of your subscription limit on the Hope For Everybody (HFE) platform.
                                    <br /><br />
                                    At this point, we recommend reviewing your usage and ensuring everything is aligned with your needs. If you continue at the same pace, you may reach your subscription limit soon.
                                    <br /><br />
                                    Here’s a quick overview of your usage:
                                    <br />
                                    <div>
                                        <strong>Current Plan:</strong> {subscription.name} <br />
                                        <strong>Usage:</strong> {threshold}% <br />
                                        <strong>Remaining:</strong> 20%
                                    </div>
                                    <br /><br />
                                    If you need more features or resources, you can upgrade your plan directly from your service provider portal: <a href="[Login Link]">Login Link</a>
                                </p>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 500; color: #0a0d14; line-height: 20px; margin-bottom: 8px; margin-top: 30px;">
                                    Should you have any questions or need assistance, our support team is here to help.
                                </p>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                    Thank you for being part of Hope For Everybody!
                                </p>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                    The HFE Team
                                </p>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px; margin-top: 30px;">
                                    For any inquiries or support, feel free to reach out to us at: <a href="mailto:[Support Email]">Support Email</a>
                                </p>
                        
                                <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                                    Visit our website: <a href="[Website Link]">Website Link</a>
                                </p>
                            </div>
                        </div>

                    """
                    await send_email(service_provider.useremail, "Alert", body)

            # Save service provider updates
            service_provider.details = json.loads(
                json.dumps(details)
            )  # Force update detection
            flag_modified(service_provider, "details")

            db.commit()
            db.refresh(service_provider)
            logger.log_info("Updated service provider client count")

        # Send welcome email
        subject = "Welcome to the Platform!"
        body = f"""
            <div>
                <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                    <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                        <a href="#" style="width:100%; text-align:center;">
                            <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                        </a>
                    </div>
                    <h2>Welcome, {client.first_name} {client.last_name}!</h2>
                    <p>You have been added as a client on our platform.</p>
                    <p>Your login credentials are:</p>
                            <ul>
                                <li><strong>Email:</strong> {client.useremail}</li>
                                <li><strong>Password:</strong> {generated_password}</li>
                            </ul>
                        For any inquiries or support, feel free to reach out to us at: <a href="mailto:[Support Email]">[Support Email]</a>
                    </p>
                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                        Visit our website: <a href="[Website Link]">[Website Link]</a>
                    </p>
                </div>
            </div>

        """
        await send_email(client.useremail, subject, body)
        logger.log_info("Welcome email sent successfully")

        return {
            "uuid": new_client.uuid,
            "created_by": client.admin_uuid,
            "profile_img": profile_img_url,
            "header_img": header_img_url,
        }

    except Exception as e:
        # logger.log_error("Unexpected error while creating client", )
        return JSONResponse(
            status_code=500, content={"message": f"Internal server error: {e!s}"}
        )


async def get_all_client(
    skip: int,
    limit: int,
    db: Session,
    name_original: str = None,
    is_activated: bool = None,
    user_id: UUID = None,
    old_new: str = None,
    category: int = None,
    zipcode: int = None,
    county: str = None,
    city: str = None,
    sort_order: str = "asc",
    sort_by: str = None,
    is_other_client: bool = False,
):
    try:
        query = None
        if is_other_client and user_id:
            logger.log_info(f"Getting other clients for {user_id}")
            service_provider = (
                db.query(models.User).filter(models.User.uuid == user_id).first()
            )
            membership = (
                db.query(models.Membership)
                .filter(models.Membership.uuid == service_provider.uuid)
                .first()
            )
            details = service_provider.details or {}
            if "service_provider" in details and membership:
                service_provider_data = details["service_provider"]
                subscription = (
                    db.query(models.Subscription)
                    .filter(
                        models.Subscription.subscription_id
                        == membership.subscription_id
                    )
                    .first()
                )
                if subscription:
                    query = db.query(models.User).filter(
                        and_(
                            models.User.created_by != user_id,
                            models.User.role_type == "client",
                            models.User.is_deleted == False,
                        )
                    )
                    if subscription.view_other_client == "local":
                        logger.log_info(f"Getting local clients for {user_id}")
                        query = query.filter(
                            models.User.details["client"]["lat"].isnot(None),
                            models.User.details["client"]["long"].isnot(None),
                            models.User.details["client"]["long"] != "null",
                            models.User.details["client"]["lat"] != "null",
                        )
                        distance_expr = 3958.8 * func.acos(
                            func.cos(
                                func.radians(cast(service_provider_data["lat"], Float))
                            )
                            * func.cos(
                                func.radians(
                                    cast(
                                        models.User.details["client"]["lat"].astext,
                                        Float,
                                    )
                                )
                            )
                            * func.cos(
                                func.radians(
                                    cast(
                                        models.User.details["client"]["long"].astext,
                                        Float,
                                    )
                                )
                                - func.radians(
                                    cast(service_provider_data["long"], Float)
                                )
                            )
                            + func.sin(
                                func.radians(cast(service_provider_data["lat"], Float))
                            )
                            * func.sin(
                                func.radians(
                                    cast(
                                        models.User.details["client"]["lat"].astext,
                                        Float,
                                    )
                                )
                            )
                        )

                        query = query.filter(
                            distance_expr <= 25  # Adding the distance condition
                        )
                    elif subscription.view_other_client == "regional":
                        logger.log_info(f"Getting regional clients for {user_id}")
                        query = query.filter(
                            models.User.details["client"]["region"].astext
                            == "region1_texas"
                        )
                    elif subscription.view_other_client == "statewide":
                        logger.log_info(f"Getting statewide clients for {user_id}")
                        query = query.filter(
                            models.User.details["client"]["state"].astext
                            == service_provider_data["state"]
                        )
                    elif subscription.view_other_client == "multistate":
                        logger.log_info(f"Getting multistate clients for {user_id}")
                        query = query.filter(
                            models.User.details["client"]["country"].astext
                            == service_provider_data["country"]
                        )
                else:
                    logger.info(
                        f"No Subscription found for the Service Provider: {user_id} with subscription id: {subscription.subscription_id}"
                    )
            else:
                logger.log_info(f"No Details found for the Service Provider: {user_id}")

        if not query:
            query = db.query(models.User).filter(models.User.role_type == "client", models.User.is_deleted == False)

            if user_id:
                query = query.filter(models.User.service_provider_ids.any(user_id))

        name = await translate_fields(name_original, fields=[])

        if is_activated is not None:
            query = query.filter(models.User.is_activated == is_activated)

        if name:
            name_parts = name.split()

            if len(name_parts) >= 2:
                query = query.filter(
                    or_(
                        and_(
                            models.User.details["client"]["first_name"].astext.ilike(
                                f"%{name_parts[0]}%"
                            ),
                            models.User.details["client"]["last_name"].astext.ilike(
                                f"%{name_parts[1]}%"
                            ),
                        ),
                        or_(
                            models.User.details["client"]["first_name"].astext.ilike(
                                f"%{name}%"
                            ),
                            models.User.details["client"]["last_name"].astext.ilike(
                                f"%{name}%"
                            ),
                            models.User.details["client"]["phone"].astext.ilike(
                                f"%{name}%"
                            ),
                            models.User.useremail.ilike(f"%{name}%"),
                            models.User.details["client"]["state"].astext.ilike(
                                f"%{name}%"
                            ),
                            models.User.details["client"]["city"].astext.ilike(
                                f"%{name}%"
                            ),
                        ),
                    )
                )
            else:
                # If the name is a single word, search in all relevant fields.
                query = query.filter(
                    or_(
                        models.User.details["client"]["first_name"].astext.ilike(
                            f"%{name}%"
                        ),
                        models.User.details["client"]["last_name"].astext.ilike(
                            f"%{name}%"
                        ),
                        models.User.details["client"]["phone"].astext.ilike(
                            f"%{name}%"
                        ),
                        models.User.useremail.ilike(f"%{name}%"),
                        models.User.details["client"]["state"].astext.ilike(
                            f"%{name}%"
                        ),
                        models.User.details["client"]["city"].astext.ilike(f"%{name}%"),
                    )
                )

        if old_new:
            filter_date = datetime.now() - timedelta(days=30)
            if old_new.lower() == "new":
                query = query.filter(models.User.created_at >= filter_date)
            elif old_new.lower() == "old":
                query = query.filter(models.User.created_at < filter_date)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid value for old_new. Use 'new' or 'old'.",
                )

        if county:
            query = query.filter(
                models.User.details["client"]["county"].astext.ilike(f"%{county}%")
            )

        if city:
            query = query.filter(
                models.User.details["client"]["city"].astext.in_([city.upper()])
            )

        if zipcode:
            query = query.filter(
                models.User.details["client"]["zip_code"].astext.ilike(f"{zipcode}")
            )

        if category:
            query = query.filter(
                cast(models.User.details["client"]["primary_need"], Integer) == category
            )
        if sort_by:
            if sort_by in [
                "name",
                "email",
                "created_at",
                "status",
            ]:
                column = {
                    "name": models.User.details["client"]["name"].astext,
                    "email": models.User.useremail,
                    "created_at": models.User.created_at,
                    "status": models.User.status,
                }.get(sort_by)

                if sort_order.lower() == "desc":
                    query = query.order_by(column.desc())
                else:
                    query = query.order_by(column.asc())

        total_client = query.count()
        clients = query.offset(skip).limit(limit).all()

        formatted_clients = []
        for client in clients:
            if not client:
                return JSONResponse(
                    status_code=404, content={"message": "No Client found"}
                )

            rating = client.details.get("client", {}).get("rating", "")
            overall_rating = rating if rating else None

            profile_img_url = f"{client.profile_img}" if client.profile_img else None
            header_img_url = f"{client.header_img}" if client.header_img else None

            role_type = (
                db.query(models.User.role_type)
                .filter(models.User.uuid == client.created_by)
                .first()
            )
            role_type_value = role_type[0] if role_type else None

            socialmedia_links = client.details.get("client", {}).get(
                "socialmedia_links", []
            )
            if isinstance(socialmedia_links, str):
                socialmedia_links = [link.strip().strip("'") for link in socialmedia_links.strip("[]").split(',')]

            elif not isinstance(socialmedia_links, list):
                socialmedia_links = []

            skills = client.details.get("client", {}).get("skills", [])
            if isinstance(skills, str):
                skills = [skills]
            elif not isinstance(skills, list):
                skills = []

            # Process secondary need: ensure it's a list
            secondary_need_ids = client.details.get("client", {}).get(
                "secondary_need", []
            )
            if isinstance(secondary_need_ids, str):
                secondary_need_ids = [secondary_need_ids]
            elif not isinstance(secondary_need_ids, list):
                secondary_need_ids = []

            # Fetch primary need: attempt to convert to integer
            primary_need_raw = client.details.get("client", {}).get(
                "primary_need", None
            )
            primary_need_id = None
            primary_need_value = ""
            if primary_need_raw:
                try:
                    primary_need_id = int(primary_need_raw)
                    primary_category = (
                        db.query(models.Category)
                        .filter(models.Category.category_id == primary_need_id)
                        .first()
                    )
                    primary_need_value = (
                        primary_category.category_name
                        if primary_category
                        and primary_category.category_name is not None
                        else ""
                    )
                except (ValueError, TypeError):
                    primary_need_id = None
                    primary_need_value = ""

            # For secondary needs, try converting each item to integer
            secondary_need_value = []
            valid_secondary_ids = []
            for item in secondary_need_ids:
                try:
                    sec_id = int(item)
                    valid_secondary_ids.append(sec_id)
                    cat_obj = (
                        db.query(models.Category)
                        .filter(models.Category.category_id == sec_id)
                        .first()
                    )
                    secondary_need_value.append(
                        cat_obj.category_name
                        if cat_obj and cat_obj.category_name is not None
                        else ""
                    )
                except (ValueError, TypeError):
                    secondary_need_value.append("")

            formatted_clients.append(
                {
                    "uuid": str(client.uuid),
                    "first_name": client.details.get("client", {}).get(
                        "first_name", ""
                    ),
                    "last_name": client.details.get("client", {}).get("last_name", ""),
                    "phone": client.details.get("client", {}).get("phone", ""),
                    "gender": client.details.get("client", {}).get("gender", ""),
                    "email": client.useremail,
                    "county": client.details.get("client", {}).get("county", ""),
                    "state": client.details.get("client", {}).get("state", ""),
                    "city": client.details.get("client", {}).get("city", ""),
                    "zip_code": str(
                        client.details.get("client", {}).get("zip_code", "")
                    ),  # Ensure zip_code is a string
                    "country": client.details.get("client", {}).get("country", ""),
                    "region": client.details.get("client", {}).get("region", ""),
                    "county_region": {
                        "county": client.details.get("client", {}).get("county", ""),
                        "region": client.details.get("client", {}).get("region", "")
                    },
                    "lat": client.details.get("client", {}).get("lat", ""),
                    "long": client.details.get("client", {}).get("long", ""),
                    "ssn": client.details.get("client", {}).get("ssn", ""),
                    "dob": client.details.get("client", {}).get("dob", ""),
                    "housing_situation": client.details.get("client", {}).get(
                        "housing_situation", ""
                    ),
                    "website_link": client.details.get("client", {}).get(
                        "website_link", ""
                    ),
                    "address_1": client.details.get("client", {}).get("address_1", ""),
                    "address_2": client.details.get("client", {}).get("address_2", ""),
                    "Question": client.details.get("client", {}).get("Question", ""),
                    "socialmedia_links": socialmedia_links,
                    "skills": skills,
                    "comments": client.details.get("client", {}).get("comments", ""),
                    "primary_need_id": primary_need_id,
                    "primary_need": primary_need_value,
                    "secondary_need_ids": valid_secondary_ids,  # key changed to plural
                    "secondary_need": secondary_need_value,
                    "resume": client.details.get("client", {}).get("resume", ""),
                    "is_activated": client.is_activated,
                    "profile_img": profile_img_url,
                    "header_img": header_img_url,
                    "created_by_role_type": role_type_value,
                    "created_by": client.created_by,
                    "approved_by": client.approved_by,
                    "updated_by": client.updated_by,
                    "updated_at": client.updated_at,
                    "created_at": client.created_at,
                    "is_deleted": client.is_deleted,
                    "deleted_by": client.deleted_by,
                    "deleted_at": client.deleted_at,
                    "rating": overall_rating,
                }
            )

        return {
            "total_client": total_client,
            "client": formatted_clients,
        }
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"message": f"An error occurred: {e!s}"}
        )


def get_client(uuid: UUID, db: Session):
    try:
        client = db.query(models.User).filter(models.User.uuid == uuid).first()

        if not client:
            return JSONResponse(
                status_code=404, content={"message": "No service provider found"}
            )

        creator = (
            db.query(models.User).filter(models.User.uuid == client.created_by).first()
        )

        if client.created_by == client.uuid:
            role_type_value = "self"
            name_value = None
        elif creator and creator.role_type == "service_provider":
            role_type_value = "service_provider"
            name_value = creator.details.get("service_provider", {}).get("name")
        else:
            role_type_value = creator.role_type if creator else "Unknown"
            name_value = "admin" if role_type_value == "admin" else None

        if client.is_deleted:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"message": "Requested Client is no longer available"},
            )

        question_value = client.details.get("client", {}).get("Question", "")

        question = client.details.get("client", {}).get("question", "")

        # Convert Enum to string if necessary
        if isinstance(question_value, schemas.QuestionEnumClient):
            question_value = question_value.value
        elif isinstance(question_value, str) and question_value.startswith(
            "QuestionEnumClient."
        ):
            question_value = question_value.split(".")[
                -1
            ].lower()  # Extract and lowercase the enum name

        rating = client.details.get("client", {}).get("rating", "")
        overall_rating = rating if rating else None

        profile_img_url = client.profile_img if client.profile_img else None
        header_img_url = client.header_img if client.header_img else None

        socialmedia_links = client.details.get("client", {}).get(
            "socialmedia_links", []
        )
        if isinstance(socialmedia_links, str):
            socialmedia_links = [link.strip().strip("'") for link in socialmedia_links.strip("[]").split(',')]
        elif not isinstance(socialmedia_links, list):
            socialmedia_links = []

        skills = client.details.get("client", {}).get("skills", [])
        if isinstance(skills, str):
            skills = [link.strip() for link in skills.split(",")]
        elif not isinstance(skills, list):
            skills = []

        # Get the data from the correct nested key
        primary_need_raw = client.details.get("client", {}).get("primary_need", None)
        secondary_need_raw = client.details.get("client", {}).get("secondary_need", [])

        # Convert primary_need_raw to int
        primary_need_id = None
        primary_need_value = None
        if primary_need_raw is not None:
            try:
                primary_need_id = int(primary_need_raw)
                primary_category = (
                    db.query(models.Category)
                    .filter(models.Category.category_id == primary_need_id)
                    .first()
                )
                primary_need_value = (
                    primary_category.category_name if primary_category else None
                )
            except (ValueError, TypeError):
                primary_need_id = None

        # Convert secondary_need_raw to a list of integers
        if isinstance(secondary_need_raw, str):
            secondary_need_raw = [secondary_need_raw]
        elif not isinstance(secondary_need_raw, list):
            secondary_need_raw = []

        secondary_need_ids = []
        secondary_need_values = []
        for item in secondary_need_raw:
            try:
                sec_id = int(item)
                secondary_need_ids.append(sec_id)
                sec_category = (
                    db.query(models.Category)
                    .filter(models.Category.category_id == sec_id)
                    .first()
                )
                secondary_need_values.append(
                    sec_category.category_name if sec_category else ""
                )
            except (ValueError, TypeError):
                secondary_need_values.append("")

        return {
            "uuid": str(client.uuid),
            "first_name": client.details.get("client", {}).get("first_name", ""),
            "last_name": client.details.get("client", {}).get("last_name", ""),
            "gender": client.details.get("client", {}).get("gender", ""),
            "phone": client.details.get("client", {}).get("phone", ""),
            "email": client.useremail,
            "county_region": {
                "county": client.details.get("client", {}).get("county", ""),
                "region": client.details.get("client", {}).get("region", "")
            },
            "state": client.details.get("client", {}).get("state", ""),
            "city": client.details.get("client", {}).get("city", ""),
            "zip_code": client.details.get("client", {}).get("zip_code", ""),
            "country": client.details.get("client", {}).get("country", ""),
            "lat": client.details.get("client", {}).get("lat", ""),
            "long": client.details.get("client", {}).get("long", ""),
            "ssn": client.details.get("client", {}).get("ssn", ""),
            "dob": client.details.get("client", {}).get("dob", ""),
            "housing_situation": client.details.get("client", {}).get(
                "housing_situation", ""
            ),
            "website_link": client.details.get("client", {}).get("website_link", ""),
            "address_1": client.details.get("client", {}).get("address_1", ""),
            "address_2": client.details.get("client", {}).get("address_2", ""),
            "Question": question_value,
            "question": question,
            "social_media_links": socialmedia_links,
            "skills": skills,
            "comments": client.details.get("client", {}).get("comments", ""),
            # Add primary need details
            "primary_need_id": primary_need_id,
            "primary_need": primary_need_value,
            # Add secondary need details
            "secondary_need_id": secondary_need_ids,
            "secondary_need": secondary_need_values,
            "resume": client.details.get("client", {}).get("resume", ""),
            "profile_img": profile_img_url,
            "header_img": header_img_url,
            "is_activated": client.is_activated,
            "created_by": client.created_by,
            "created_by_role_type": role_type_value,
            "created_by_name": name_value,
            "updated_by": client.updated_by,
            "updated_at": client.updated_at,
            "created_at": client.created_at,
            "is_deleted": client.is_deleted,
            "deleted_by": client.deleted_by,
            "deleted_at": client.deleted_at,
            "rating": overall_rating,
        }
    except HTTPException as e:
        raise e


# =======================================================================


async def update_client(
    request: Request,
    client_uuid: UUID4,
    useremail:EmailStr,
    updated_client_original: schemas.UpdateClient,
    profile_img: UploadFile = None,
    header_img: UploadFile = None,
    avatar_selection: str = None,
    resume:UploadFile | str | None = None,
    db: Session = Depends(get_db),
):
    try:
        updated_client = await translate_fields(
            updated_client_original,
            fields=[
                "first_name",
                "last_name",
                "gender",
                "housing_situation",
                "Question",
                "question",
                "address_1",
                "address_2",
                "county",
                "city",
                "state",
                "country",
            ],
        )

        client = db.query(models.User).filter(models.User.uuid == client_uuid).first()
        if not client:
            return JSONResponse(
                status_code=404, content={"message": "Client not found"}
            )

        updated_clients = updated_client.model_dump(exclude_unset=True)
        update_data = {"updated_by": updated_client.admin_uuid}

        profile_img_url = client.profile_img
        header_img_url = client.header_img
        resume_old = client.details.get("client", {}).get("resume", None)
        avatar_list = [
            f"/avatars/{img}"
            for img in os.listdir(AVATAR_FOLDER)
            if img.endswith(".svg")
        ]

        if profile_img and not avatar_selection:
            profile_img_url = save_uploaded_file(profile_img, request, "hfe_images")

        elif profile_img_url and avatar_selection:
            profile_img_url = (
                f"{str(request.base_url).rstrip('/')}{avatar_selection}"
                if avatar_list
                else None
            )

        if header_img:
            header_img_url = save_uploaded_file(header_img, request, "hfe_images")

        details_updates = {}

        if useremail:
            update_data['useremail'] = useremail
            
        if profile_img_url != client.profile_img:
            update_data["profile_img"] = profile_img_url
            details_updates["profile_img"] = profile_img_url

        if header_img_url != client.header_img:
            update_data["header_img"] = header_img_url
            details_updates["header_image"] = header_img_url

        for key, value in updated_clients.items():
            if key in client.details.get("client", {}):
                if value is not None:
                    details_updates[key] = value

        if resume is None and resume_old is not None:
            details_updates["resume"] = None
        elif resume is not None:
            resume_url = save_uploaded_pdf(resume, request,"resume",mount="resume")
            if resume_url:
                details_updates["resume"] = resume_url

        if details_updates:
            for key, value in details_updates.items():
                json_value = json.dumps(value, default=str)
                db.query(models.User).filter(models.User.uuid == client_uuid).update(
                    {
                        "details": func.jsonb_set(
                            models.User.details, f"{{client,{key}}}", json_value
                        )
                    }
                )
        if update_data:
            db.query(models.User).filter(models.User.uuid == client_uuid).update(
                update_data
            )

        db.commit()
        db.refresh(client)

        return {
            "client_uuid": client.uuid,
            "updated_at": datetime.now(),
            "updated_by": updated_client.admin_uuid,
            "profile_image": client.profile_img,
            "header_image": client.header_img,
        }

    except HTTPException as e:
        db.rollback()
        raise e


def status_client(client_uuid: UUID4, db: Session):
    try:
        del_client = (
            db.query(models.User).filter(models.User.uuid == client_uuid).first()
        )

        if del_client is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Client in not found")
        del_client.is_activated = not del_client.is_activated
        db.commit()
        return {
            "detail": "Client status change successfully",
            "is_activated": del_client.is_activated,
        }

    except HTTPException as e:
        raise e


def delete_client(uuid: UUID, deleted_by: schemas.SoftDeleteClient, db: Session):
    try:
        del_client = db.query(models.User).filter(models.User.uuid == uuid).first()

        if not del_client:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"message": "No client found"},
            )

        if del_client.is_deleted == True:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"message": "Client is already deleted"},
            )
        else:
            del_client.is_deleted = True
            del_client.deleted_by = deleted_by.deleted_by
            del_client.deleted_at = datetime.now()

        db.commit()
        return {
            "deleted_by": deleted_by.deleted_by,
            "details": "Client deleted successfully",
        }
    except HTTPException as e:
        raise e


def client_rating(rating: schemas.Rating, db: Session):
    try:
        # Validate if the service provider exists
        service_provider = (
            db.query(models.User)
            .filter(models.User.uuid == rating.service_provider_id)
            .first()
        )
        if not service_provider:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content="Service provider not found",
            )

        # Validate if the client exists
        db_client = (
            db.query(models.User).filter(models.User.uuid == rating.client_id).first()
        )
        if not db_client:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content="Client not found"
            )

        # Calculate the average rating
        rating_fields = [
            rating.hygiene,
            rating.communication,
            rating.politeness,
            rating.gratitude,
            rating.addiction_acitivity,
            rating.illegal_activity,
        ]
        average_rating = sum(rating_fields) / len(rating_fields)

        # Create a new rating instance with the calculated average
        new_rating = models.Ratings(
            client_id=rating.client_id,
            service_provider_id=rating.service_provider_id,
            hygiene=rating.hygiene,
            communication=rating.communication,
            politeness=rating.politeness,
            gratitude=rating.gratitude,
            addiction_acitivity=rating.addiction_acitivity,
            illegal_activity=rating.illegal_activity,
            comments=rating.comments,
            average_rating=average_rating,  # ✅ Set calculated value
        )

        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)

        return new_rating

    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e


def get_all_questions(
    db: Session, skip: int = 0, limit: int = 10
):  # -> List[schemas.QuestionResponse]:
    questions = db.query(models.Questionnaires).offset(skip).limit(limit).all()
    total_questions = db.query(models.Questionnaires).count()
    return {"total_questions": total_questions, "questions": questions}


def get_question(question_id: int, db: Session):
    question = (
        db.query(models.Questionnaires)
        .filter(models.Questionnaires.id == question_id)
        .first()
    )
    return question


def favorite_user(fav_user: schemas.FavoriteUser, db: Session):
    favourited_to_user = (
        db.query(models.User).filter(models.User.uuid == fav_user.favorite_to).first()
    )
    favourited_by_user = (
        db.query(models.User).filter(models.User.uuid == fav_user.favorite_by).first()
    )

    if not favourited_to_user:
        raise HTTPException(status_code=404, detail="favourited_to_user not found")

    if not favourited_by_user:
        raise HTTPException(status_code=404, detail="favourited_by_user not found")

    existing_fav = (
        db.query(models.FavouriteBlocked)
        .filter(
            models.FavouriteBlocked.favourited_by == fav_user.favorite_by,
            models.FavouriteBlocked.favourited_to == fav_user.favorite_to,
        )
        .first()
    )

    if existing_fav:
        # If the provider is already favorited, remove the favorite (unfavorite)
        db.delete(existing_fav)
        db.commit()
        return {
            "message": f"{favourited_to_user.role_type} is unfavorited by {favourited_by_user.role_type}"
        }

    # If not favorited, add it
    new_fav = models.FavouriteBlocked(
        favourited_by=favourited_by_user.uuid,
        favourited_to=favourited_to_user.uuid,
        created_at=datetime.now(),
    )

    db.add(new_fav)
    db.commit()
    db.refresh(new_fav)

    return {
        "message": f"{favourited_to_user.role_type} is favorited by {favourited_by_user.role_type}"
    }


def block_user(block_user: schemas.BlockedUser, db: Session):
    blocked_to_user = (
        db.query(models.User).filter(models.User.uuid == block_user.blocked_to).first()
    )
    blocked_by_user = (
        db.query(models.User).filter(models.User.uuid == block_user.blocked_by).first()
    )

    if not blocked_to_user:
        raise HTTPException(status_code=404, detail="blocked_to_user not found")

    if not blocked_by_user:
        raise HTTPException(status_code=404, detail="blocked_by_user not found")

    existing_block = (
        db.query(models.FavouriteBlocked)
        .filter(
            models.FavouriteBlocked.blocked_by == block_user.blocked_by,
            models.FavouriteBlocked.blocked_to == block_user.blocked_to,
        )
        .first()
    )

    if existing_block:
        # If the user is already blocked, remove the block (unblock)
        db.delete(existing_block)
        db.commit()
        return {
            "message": f"{blocked_to_user.role_type} is unblocked by {blocked_by_user.role_type}"
        }

    # If not blocked, add it
    new_block = models.FavouriteBlocked(
        blocked_by=blocked_by_user.uuid,
        blocked_to=blocked_to_user.uuid,
        created_at=datetime.now(),
    )

    db.add(new_block)
    db.commit()
    db.refresh(new_block)

    return {
        "message": f"{blocked_to_user.role_type} is blocked by {blocked_by_user.role_type}"
    }


def get_favourite_blocked_users(user_uuid: UUID, type: str, db: Session):
    if type not in ["favorite", "blocked"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid type. Choose either 'favorite' or 'blocked'",
        )

    query = db.query(models.FavouriteBlocked)

    if type == "favorite":
        query = query.filter(models.FavouriteBlocked.favourited_by == user_uuid)
    elif type == "blocked":
        query = query.filter(models.FavouriteBlocked.blocked_by == user_uuid)

    results = query.all()

    response_data = []
    for record in results:
        if type == "favorite":
            user = (
                db.query(models.User)
                .filter(models.User.uuid == record.favourited_to)
                .first()
            )
        else:
            user = (
                db.query(models.User)
                .filter(models.User.uuid == record.blocked_to)
                .first()
            )

        if user:
            response_data.append(
                {
                    "uuid": user.uuid,
                    # "name": user.,
                    "role_type": user.role_type,
                }
            )

    return response_data


async def bulk_client_upload(admin_uuid: UUID, file: UploadFile, db: Session):
    REQUIRED_FIELDS = [
        "first_name",
        "last_name",
        "dob",
        "ssn",
        "gender",
        "email",
        "address_1",
        "city",
        "state",
        "zip_code",
        "county",
    ]
    OPTIONAL_FIELDS = [
        "profile_img",
        "header_img",
        "phone",
        "address_2",
        "website_link",
    ]

    contents = await file.read()

    # Determine file type and read accordingly
    file_extension = file.filename.split(".")[-1].lower()

    if file_extension == "csv":
        df = pd.read_csv(io.BytesIO(contents))
    elif file_extension in ["xls", "xlsx"]:
        df = pd.read_excel(io.BytesIO(contents))
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only CSV and Excel files are supported.",
        )

    generated_password = generate_random_password()
    encrypted_password = encrypt_password(generated_password, secret_key)

    # Check for missing required columns
    missing_columns = [col for col in REQUIRED_FIELDS if col not in df.columns]
    if missing_columns:
        raise HTTPException(
            status_code=400, detail=f"Missing columns: {', '.join(missing_columns)}"
        )

    for _, row in df.iterrows():
        if db.query(models.User).filter(models.User.useremail == row["email"]).first():
            continue  # Skip duplicate emails

        user_uuid = uuid.uuid4()

        # Create client details dynamically
        client_details = {
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "dob": row["dob"],
            "ssn": row["ssn"],
            "gender": row["gender"],
            "address_1": row["address_1"],
            "city": row["city"],
            "state": row["state"],
            "zip_code": row["zip_code"],
            "county": row["county"],
            "email": row["email"],
        }
        body = f"""
                <div>
                    <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                        <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                            <a href="#" style="width:100%; text-align:center;">
                                <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                            </a>
                        </div>
                        <h2>Welcome, {row["first_name"]} {row["last_name"]}!</h2>
                        <p>You have been added as a client on our platform.</p>
                        <p>Your login credentials are:</p>
                                <ul>
                                    <li><strong>Email:</strong> {row["email"]}</li>
                                    <li><strong>Password:</strong> {generated_password}</li>
                                </ul>
                            For any inquiries or support, feel free to reach out to us at: <a href="mailto:[Support Email]">[Support Email]</a>
                        </p>
                
                        <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                            Visit our website: <a href="[Website Link]">[Website Link]</a>
                        </p>
                    </div>
                </div>
                """
        await send_email(
            client_details["email"], "Welcome, You are added as a Client!", body
        )

        # Add optional fields if present, otherwise set them to None
        for field in OPTIONAL_FIELDS:
            client_details[field] = (
                row[field] if field in df.columns and pd.notna(row[field]) else None
            )

        user = models.User(
            uuid=user_uuid,
            useremail=row["email"],
            password=encrypted_password,
            role_type="client",
            created_by=admin_uuid,
            is_activated=True,
            status="verified",
            details={"client": client_details},
        )
        db.add(user)

    db.commit()
    return {"message": "Clients uploaded successfully"}


async def bulk_service_provider_upload(admin_uuid: UUID, file: UploadFile, db: Session):
    REQUIRED_FIELDS = ["contact_name", "phone", "email"]
    OPTIONAL_FIELDS = ["service_provider_type", "name", "website_link", "comments","state","zip_code"]

    SAVE_PATH = os.path.join(BASE_DIR,"import_provider")
    contents = await file.read()

    total_count = 0
    success_count = 0
    fail_count = 0

    success_list = []
    failed_list = []
    # Determine file type and read accordingly
    file_extension = file.filename.split(".")[-1].lower()

    if file_extension == "csv":
        df = pd.read_csv(io.BytesIO(contents))
    elif file_extension in ["xls", "xlsx"]:
        try:
            import openpyxl  # Ensure openpyxl is available for reading Excel files

            df = pd.read_excel(io.BytesIO(contents))
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Missing required dependency: openpyxl. Install it using 'pip install openpyxl'.",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only CSV and Excel files are supported.",
        )

    # Check for missing required columns
    missing_columns = [col for col in REQUIRED_FIELDS if col not in df.columns]
    if missing_columns:
        raise HTTPException(
            status_code=400, detail=f"Missing columns: {', '.join(missing_columns)}"
        )
    file_path_json = {}
    for _, row in df.iterrows():
        total_count += 1
        if db.query(models.User).filter(models.User.useremail == row["email"]).first():
            fail_count += 1
            failed_list.append(row.to_dict())
            continue

        user_uuid = uuid.uuid4()
        generated_password = generate_random_password()
        encrypted_password = encrypt_password(generated_password, secret_key)
        # Create service provider details dynamically
        service_provider_details = {
            "contact_name": row["contact_name"],
            "contact_title": row["contact_title"],
            "phone": row["phone"],
            "email": row["email"],
        }
        await send_email(
            service_provider_details["email"],
            "Welcome, You are added as a Service Provider!",
            f"Your username is:{service_provider_details['email']} \n Your password is: {generated_password}",
        )

        # Add optional fields if present, otherwise set them to None
        for field in OPTIONAL_FIELDS:
            service_provider_details[field] = (
                row[field] if field in df.columns and pd.notna(row[field]) else None
            )

        user = models.User(
            uuid=user_uuid,
            useremail=row["email"],
            password=encrypted_password,
            role_type="service_provider",
            created_by=admin_uuid,
            status="verified",
            details={"service_provider": service_provider_details},
            is_imported = True
        )
        success_list.append(row.to_dict())
        # increment the success count 
        success_count += 1
        db.add(user)
        db.commit()
        db.refresh(user)

    if len(failed_list) > 0:
        file_path_json.update({"fail":os.path.join(SAVE_PATH,f"{os.path.splitext(file.filename)[0]}_failed.csv")})
        df_failed = pd.DataFrame(failed_list)
        df_failed.to_csv(
            os.path.join(SAVE_PATH,f"{os.path.splitext(file.filename)[0]}_failed.csv"), index=False
        )
    
    if len(success_list) > 0:
        file_path_json.update({"success":os.path.join(SAVE_PATH,f"{os.path.splitext(file.filename)[0]}_success.csv")})
        df_success = pd.DataFrame(success_list)
        df_success.to_csv(
            os.path.join(SAVE_PATH,f"{os.path.splitext(file.filename)[0]}_success.csv"), index=False
        )
    
    import_data = models.ExportData(
            filename = file.filename,
            total_counts = total_count,
            success_counts = success_count,
            fail_counts = fail_count,
            upload_date = datetime.now(),
            file_path = file_path_json,
            uploaded_by = admin_uuid,
            role_type = "Service Provider"
        )
    db.add(import_data)
    db.commit()
    db.refresh(import_data)

    return {
        'success_count': success_count,
        'fail_count': fail_count,
        'total_count':total_count
    }

def download_imported_file(id:int,download_type:str,db:Session):

    file_record = db.query(models.ExportData.file_path).filter(models. ExportData.id == id).first()
    
    if not file_record:
        return {"message": "Record not found", "status": 404}

    file_data = file_record[0]
    file_key = 'success' if download_type == 'success' else 'fail'
    file_path = file_data.get(file_key)

    if not file_path or not os.path.exists(file_path):
        return {"message": "File not found", "status": 404}

    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream"
    )
async def bulk_upload_categories(admin_uuid: UUID, file: UploadFile, db: Session):
    REQUIRED_FIELDS = ["category_name"]

    contents = await file.read()

    # Determine file type and read accordingly
    file_extension = file.filename.split(".")[-1].lower()

    if file_extension == "csv":
        df = pd.read_csv(io.BytesIO(contents))
    elif file_extension in ["xls", "xlsx"]:
        try:
            import openpyxl  # Ensure openpyxl is installed

            df = pd.read_excel(io.BytesIO(contents))
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Missing required dependency: openpyxl. Install it using 'pip install openpyxl'.",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only CSV and Excel files are supported.",
        )

    # Check for missing required columns
    missing_columns = [col for col in REQUIRED_FIELDS if col not in df.columns]
    if missing_columns:
        raise HTTPException(
            status_code=400, detail=f"Missing columns: {', '.join(missing_columns)}"
        )

    # Check if file contains subcategory column
    has_subcategory = "sub_category_name" in df.columns

    # Group rows by category name to process each category with its subcategories
    for category_name, group in df.groupby("category_name"):
        # Check if category already exists
        category_obj = (
            db.query(models.Category)
            .filter(models.Category.category_name == category_name)
            .first()
        )

        if not category_obj:
            # Create new category
            category_obj = models.Category(
                category_name=category_name, created_by=admin_uuid
            )
            db.add(category_obj)
            db.flush()  # Assign an ID for FK references in subcategories

        # If subcategories exist, process them
        if has_subcategory:
            for _, row in group.iterrows():
                sub_cat_name = row.get("sub_category_name")
                if pd.notna(sub_cat_name):
                    # Check if subcategory already exists
                    existing_sub = (
                        db.query(models.SubCategory)
                        .filter(
                            models.SubCategory.category_id == category_obj.category_id,
                            models.SubCategory.sub_category_name == sub_cat_name,
                        )
                        .first()
                    )
                    if not existing_sub:
                        subcategory_obj = models.SubCategory(
                            category_id=category_obj.category_id,
                            sub_category_name=sub_cat_name,
                            created_by=admin_uuid,
                        )
                        db.add(subcategory_obj)

    db.commit()
    return {"message": "Categories and subcategories uploaded successfully"}


def generate_client_data(db: Session):
    """Fetches client data and returns it as a list of dictionaries."""
    clients = db.query(models.User).filter(models.User.role_type == "client").all()

    data = []
    for client in clients:
        client_details = client.details.get("client", {})

        # Fetch category_id from details JSON
        category_id = client_details.get("category_id")

        # Initialize category_name to avoid UnboundLocalError
        category_name = ""

        # Get category name from Category table if category_id is available
        if category_id:
            if isinstance(category_id, str):
                category_ids = [
                    int(cat.strip())
                    for cat in category_id.split(",")
                    if cat.strip().isdigit()
                ]
            else:
                category_ids = [category_id] if isinstance(category_id, int) else []

            if category_ids:
                categories = (
                    db.query(models.Category)
                    .filter(models.Category.category_id.in_(category_ids))
                    .all()
                )
                category_name = ", ".join([cat.category_name for cat in categories])

        # Get stored profile and header image URLs directly
        profile_img_url = client.profile_img or ""  # Fetch from User table
        header_img_url = client.header_img or ""  # Fetch from User table

        # Prepare dictionary row
        row = {
            "first_name": client_details.get("first_name", ""),
            "last_name": client_details.get("last_name", ""),
            "dob": client_details.get("dob", ""),
            "ssn": client_details.get("ssn", ""),
            "gender": client_details.get("gender", ""),
            "housing_situation": client_details.get("housing_situation", ""),
            "address_1": client_details.get("address_1", ""),
            "address_2": client_details.get("address_2", ""),
            "city": client_details.get("city", ""),
            "county": client_details.get("county", ""),
            "state": client_details.get("state", ""),
            "zip_code": client_details.get("zip_code", ""),
            "phone": client_details.get("phone", ""),
            "email": client_details.get("email", ""),
            "socialmedia_links": client_details.get("socialmedia_links", ""),
            "website_link": client_details.get("website_link", ""),
            "comments": client_details.get("comments", ""),
            "Question": client_details.get("Question", ""),
            "question": client_details.get("question", ""),
            "category_name": category_name,
            "profile_img": profile_img_url,
            "header_img": header_img_url,
        }
        data.append(row)

    return data


def generate_csv(data):
    """Generates a CSV file from client data."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)
    return output


def generate_excel(data):
    """Generates an Excel file from client data."""
    output = io.BytesIO()
    df = pd.DataFrame(data)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Clients")
    output.seek(0)
    return output


def generate_service_provider_csv(db: Session):
    """Generate a CSV file containing service provider data."""
    service_providers = (
        db.query(models.User).filter(models.User.role_type == "service_provider").all()
    )

    header = [
        "useremail",
        "status",
        "name",
        "contact_title",
        "contact_name",
        "contact_email",
        "tax_id",
        "phone",
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)

    for sp in service_providers:
        sp_details = sp.details.get("service_provider", {}) if sp.details else {}

        row = [
            sp.useremail,
            sp.status,
            sp_details.get("name"),
            sp_details.get("contact_title"),
            sp_details.get("contact_name"),
            sp_details.get("contact_email"),
            sp_details.get("tax_id"),
            sp_details.get("phone"),
        ]
        writer.writerow(row)

    output.seek(0)
    return output


def generate_service_provider_excel(db: Session):
    """Generate an Excel file containing service provider data."""
    service_providers = (
        db.query(models.User).filter(models.User.role_type == "service_provider").all()
    )

    data = []
    for sp in service_providers:
        sp_details = sp.details.get("service_provider", {}) if sp.details else {}

        data.append(
            {
                "User Email": sp.useremail,
                "Status": sp.status,
                "Name": sp_details.get("name"),
                "Contact Title": sp_details.get("contact_title"),
                "Contact Name": sp_details.get("contact_name"),
                "Contact Email": sp_details.get("contact_email"),
                "Tax ID": sp_details.get("tax_id"),
                "Phone": sp_details.get("phone"),
            }
        )

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Service Providers")

    output.seek(0)
    return output


def generate_category_csv(db: Session):
    # Fetch categories and their subcategories
    data = (
        db.query(models.Category.category_name, models.SubCategory.sub_category_name)
        .join(
            models.SubCategory,
            models.Category.category_id == models.SubCategory.category_id,
            isouter=True,
        )
        .all()
    )

    # Create an in-memory CSV file
    output = io.StringIO()
    writer = csv.writer(output)

    # Write CSV Header
    writer.writerow(["category_name", "sub_category_name"])

    # Write data rows
    for category_name, sub_category_name in data:
        writer.writerow(
            [category_name, sub_category_name or ""]
        )  # Handle null subcategories

    output.seek(0)  # Reset file pointer for reading

    return output  # Return CSV file-like object


def change_password(uuid: UUID, current_password: str, new_password: str, db: Session):
    # Fetch the existing client
    client = db.query(models.User).filter(models.User.uuid == uuid).first()
    if not client:
        return {"error": "User not found"}

    decrypted_password = decrypt_password(client.password, secret_key)

    if not decrypted_password == current_password:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Invalid current password"},
        )

    encrypted_new_password = encrypt_password(new_password, secret_key)

    # Check if the new encrypted password is the same as the current password
    if current_password == new_password:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "Enter a different password"},
        )

    # Update with the new password
    client.password = encrypted_new_password
    db.commit()
    db.refresh(client)
    return {"message": "Password changed successfully"}


def email_validation(useremail: EmailStr, db: Session):
    useremailexist = (
        db.query(models.User).filter(models.User.useremail == useremail ,models.User.is_deleted == False).first()
    )
    db.close()
    
    if useremailexist:
        return {
            "status":status.HTTP_409_CONFLICT,
            "message": "User email already exist",
            "is_imported": useremailexist.is_imported,
            "is_claimed":useremailexist.is_claimed
        }


def get_overview_dashboard(db: Session):
    total_sub_admins = (
        db.query(models.User).filter(models.User.role_type == "sub_admin").count()
    )
    total_service_provider = (
        db.query(models.User)
        .filter(models.User.role_type == "service_provider")
        .count()
    )
    total_client = (
        db.query(models.User).filter(models.User.role_type == "client").count()
    )
    active_subadmin = (
        db.query(models.User)
        .filter(models.User.role_type == "sub_admin", models.User.is_activated == True)
        .count()
    )
    active_service_provider = (
        db.query(models.User)
        .filter(
            models.User.role_type == "service_provider",
            models.User.is_activated == True,
        )
        .count()
    )
    active_client = (
        db.query(models.User)
        .filter(models.User.role_type == "client", models.User.is_activated == True)
        .count()
    )
    return {
        "total_sub_admins": total_sub_admins,
        "total_service_provider": total_service_provider,
        "total_client": total_client,
        "active_subadmin": active_subadmin,
        "active_service_provider": active_service_provider,
        "active_client": active_client,
        "Inactive_subadmin": total_sub_admins - active_subadmin,
        "Inactive_service_provider": total_service_provider - active_service_provider,
        "Inactive_client": total_client - active_client,
    }


async def send_contact_us_mail(data):
    """
    Send email to admin about the contact us request from client
    """
    
    logger.log_info("Send contact us mail to admin")
    
    try:
        if data.type == "adbanner":
            body = templates.get_template("contactus.html").render(
                name = data.name,
                role_type = data.roleType,
                address = data.address,
                email = data.email,
                number = data.phone,
                website = data.website
            )
            await send_email(os.getenv("ADMIN_EMAIL"),f"New Contact Request from {data.name}", body)
        else:
            body = templates.get_template("contactus.html").render(
                name = data.name,
                email = data.email,
                message = data.message,
            )
        await send_email(os.getenv("ADMIN_EMAIL"), f"New Contact Request from {data.name}", body)
        return {"status":200,"message": "Mail sent successfully"}
    except Exception as e:
        logger.log_error("Error while sending contact us mail to admin")
        return {"status":404,"error": "Something went wrong while sending contact us mail to admin"}
        
            

async def send_titanium_mail(data, db):
    """
    Send email to admin about the request of titanium plan from service provider
    """
    user_obj = (
        db.query(models.User).filter(models.User.uuid == data.current_user).first()
    )

    if not user_obj:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"message": "User not found"}
        )
    if user_obj.role_type != 'service_provider':
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "User is not a service provider"},
        )

    service_provider = user_obj.details.get("service_provider")
    if not service_provider:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "Service provider details not found"},
        )

    body = f"""<div>
                <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                    <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                        <a href="#" style="width:100%; text-align:center;">
                            <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                        </a>
                    </div>

                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14;">
                        Hi Team,
                    </p>

                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                        We’d like to inform you that the following service provider has opted for the <strong>Titanium Plan</strong> on the Hope For Everybody (HFE) platform.
                        <br /><br />
                        As per the process, please reach out to them to discuss their requirements, finalize the terms, and configure their custom setup.
                    </p>

                    <div style="margin-top: 15px; margin-bottom: 15px;">
                        <strong>Service Provider Details:</strong><br />
                        <strong>Name:</strong> {service_provider.get("contact_name")} <br />
                        <strong>Organization:</strong> {service_provider.get("name")} <br />
                        <strong>Email:</strong> {service_provider.get("email")} <br />
                        <strong>Phone Number:</strong> {service_provider.get("number")} <br />
                        <strong>Location:</strong> {service_provider.get("city")} <br />
                    </div>

                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                        Please ensure that the following topics are covered during the discussion:
                    </p>

                    <ul style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 22px; padding-left: 20px;">
                        <li>Custom access settings (location-based visibility, client access permissions, etc.)</li>
                        <li>Number of clients they intend to manage</li>
                        <li>Risk-reward analysis requirements (if applicable)</li>
                        <li>Custom pricing agreement</li>
                        <li>Additional requests or feature access (if any)</li>
                    </ul>

                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                        Once the conversation is complete, kindly update the admin panel with the agreed terms and assign the Titanium Plan accordingly.
                    </p>

                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                        Let us know if you need any support during this process.
                    </p>

                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px; margin-top: 30px;">
                        Best regards,<br />
                        Support team<br />
                    </p>
                </div>
            </div>
            """

    logger.log_info(f"Sending email to admin about titanium plan request")
    status_code = await send_email(
        "support@hopeforeverybody.org", "New Titanium Plan Subscription - Action Required", body
    )
    

    if status_code:
        user_obj.is_titanium_requested = True
        db.commit()
        db.refresh(user_obj)
        logger.log_info("Email sent successfully to admin about titanium plan request")
    else:
        logger.log_error("Failed to send email to admin about titanium plan request")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Failed to send email to admin"},
        )
    

    return JSONResponse(
        status_code=status.HTTP_200_OK, content={"message": "Email sent successfully"}
    )
