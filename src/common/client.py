import json
import os
import uuid
from enum import Enum

from fastapi import Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import UUID4, EmailStr
from sqlalchemy import UUID, func, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.api import schemas
from src.api.schemas import (
    CreateClient,
    UpdateClientSetting,
)
from src.authentication.encryption import encrypt_password, secret_key
from src.common.email_service import send_email
from src.common.translate import translate_fields
from src.common.user import save_uploaded_file, save_uploaded_pdf
from src.configs import database
from src.configs.config import logger
from src.models import models
from src.routers.chat import manager

get_db = database.get_db


async def create_client_self(
    request: Request,
    client_original: CreateClient,
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    avatar_selection: str | None = None,
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    try:
        client = await translate_fields(
            client_original,
            fields=[
                "first_name",
                "last_name",
                "gender",
                "housing_situation",
                "Question",
                "address_1",
                "address_2",
                "city",
                "county",
                "state",
                "country",
            ],
        )

        user = (
            db.query(models.User)
            .filter(models.User.useremail == client.useremail)
            .first()
        )

        if user and user.is_deleted == False:
            return JSONResponse(
                status_code=400, content={"message": "Email already exists"}
            )

        if profile_img:
            allowed_types = ["image/jpeg", "image/png"]
            if profile_img.content_type not in allowed_types:
                return JSONResponse(
                    status_code=400,
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

        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        AVATAR_DIR = os.path.join(BASE_DIR, "avatars")

        # Handle avatar selection only if no profile image is uploaded
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

        # If both profile_img_url and avatar_selection are not provided, store None in the database
        if not profile_img_url:
            profile_img_url = None

        resume_url = (
            save_uploaded_pdf(resume, request, folder="resume", mount="resume")
            if resume
            else None
        )
        encrypted_password = encrypt_password(client.password, secret_key)

        primary_need = (
            db.query(models.Category)
            .filter(models.Category.category_id == client.primary_need)
            .first()
        )
        secondary_need = client.secondary_need or []

        new_client = models.User(
            useremail=client.useremail,
            password=encrypted_password,
            role_type="client",
            profile_img=profile_img_url,
            header_img=header_img_url,
            is_activated=True,
            status="pending",
            service_provider_type="None",
            details={
                "client": {
                    "first_name": client.first_name,
                    "last_name": client.last_name,
                    "dob": client.dob,
                    "ssn": client.ssn,
                    "gender": client.gender,
                    "housing_situation": client.housing_situation,
                    "Question": client.Question,
                    "address_1": client.address_1,
                    "address_2": client.address_2,
                    "county": client.county,
                    "city": client.city,
                    "state": client.state,
                    "country": client.country,
                    "zip_code": client.zip_code,
                    "region": client.region,
                    "lat": client.lat,
                    "long": client.long,
                    "phone": client.phone,
                    "website_link": client.website_link,
                    "socialmedia_links": client.socialmedia_links,
                    "question": client.question,
                    # "primary_need": primary_need,
                    "primary_need": primary_need.category_id if primary_need else None,
                    "secondary_need": secondary_need,
                    # "category_id": category_id,
                    "resume": resume_url,
                    "skills": client.skills,
                }
            },
        )
        db.add(new_client)
        db.flush()
        new_client.created_by = new_client.uuid
        db.commit()
        db.refresh(new_client)

        # notification_msg = f"New client created: {client.first_name} {client.last_name} ({client.useremail})"
        # await manager.broadcast(notification_msg)
        logger.log_info("Notification broadcast to admin dashboard")
        logger.log_info("Sending email to the client")
        client_details = new_client.details.get('client')
        subject = "Welcome to the Platform!"
        body = f"""
            <div>
                <div style="margin: 50px auto; width: 60%; font-family: Inter;">
                    <div style="padding: 12px; background-color: #efe9d9; display: flex; border-radius: 6px; margin-bottom: 30px;">
                        <a href="#" style="width:100%; text-align:center;">
                            <img src="http://45.248.33.189:8100/images/HFElogo.png" alt="Logo" />
                        </a>
                    </div>
                    <h2>Welcome, {client_details.get('first_name')} {client_details.get('last_name')}!</h2>
                    <p>You have been added as a client on our platform.</p>
                    <p>Your login credentials are:</p>
                            <ul>
                                <li><strong>Email:</strong> {new_client.useremail}</li>
                                <li><strong>Password:</strong> {client.password}</li>
                            </ul>
                        For any inquiries or support, feel free to reach out to us at: <a href="mailto:{os.getenv('SUPPORT_EMAIL')}">[Support Email]</a>
                    </p>
                    <p style="font-size: 16px; font-family: Inter; font-weight: 400; color: #0a0d14; line-height: 20px;">
                        Visit our website: <a href={os.getenv('WEBSITE_URL')}>[Website Link]</a>
                    </p>
                </div>
            </div>

        """
        await send_email(new_client.useremail, subject, body)

        return new_client

    except Exception as e:
        return JSONResponse(
            status_code=500, content={"message": f"Internal server error: {e!s}"}
        )


async def update_client_self(
    request: Request,
    client_uuid: UUID4,
    useremail:EmailStr,
    updated_client_original: UpdateClientSetting,
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    # avatar_selection: Optional[str] = None,
    resume: UploadFile | str | None = File(None),
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
                "address_1",
                "address_2",
                "city",
                "county",
                "state",
                "country",
                "useremail",
                "phone"
            ],
        )

        client = db.query(models.User).filter(models.User.uuid == client_uuid).first()
        if not client:
            return JSONResponse(
                status_code=404, content={"message": "Client not found"}
            )

        updated_clients = updated_client.model_dump(exclude_unset=True)
        update_data = {"updated_by": updated_client.client_uuid}

        # Maintain existing values unless updated
        profile_img_url = client.profile_img
        header_img_url = client.header_img
        resume_old = client.details.get("client", {}).get("resume", None)
        


        if profile_img:
            profile_img_url = save_uploaded_file(profile_img, request, "hfe_images")
        # Handle header image update
        if header_img:
            header_img_url = save_uploaded_file(header_img, request, "hfe_images")



        # Check if any updates are needed before modifying the database
        details_updates = {}

        if resume:
            resume_url = save_uploaded_pdf(resume, request) if resume else None
            if resume_url:
                details_updates["resume"] = resume_url
        if useremail:
            update_data["useremail"] = useremail
        # Update only if profile image has changed
        if profile_img_url != client.profile_img:
            update_data["profile_img"] = profile_img_url
            details_updates["profile_img"] = profile_img_url

        # Update only if header image has changed
        if header_img_url != client.header_img:
            update_data["header_img"] = header_img_url
            details_updates["header_image"] = header_img_url

        if resume is None and resume_old is not None:
            details_updates["resume"] = None
        elif resume is not None:
            resume_url = save_uploaded_pdf(resume, request,"resume",mount="resume")
            if resume_url:
                details_updates["resume"] = resume_url

        if (
            updated_client.Question is not None
            and updated_client.Question
            != client.details.get("client", {}).get("Question")
        ):
            details_updates["Question"] = updated_client.Question

        # Update other fields in the details dictionary
        for key, value in updated_clients.items():
            if value is not None:
                if isinstance(value, Enum):
                    details_updates[key] = value.value
                else:
                    details_updates[key] = value

        # Explicitly add primary_need and secondary_need to details_updates
        if updated_client.primary_need is not None:
            details_updates["primary_need"] = updated_client.primary_need

        if updated_client.secondary_need is not None:
            details_updates["secondary_need"] = updated_client.secondary_need

        # Apply the updates only if there are changes
        if details_updates:
            for key, value in details_updates.items():
                json_value = json.dumps(value, default=str)
                # Always store updates under details["client"][key]
                db.query(models.User).filter(models.User.uuid == client_uuid).update(
                    {
                        "details": func.jsonb_set(
                            models.User.details, f"{{client,{key}}}", json_value
                        )
                    }
                )

        # Apply changes if any updates are needed
        if update_data:
            db.query(models.User).filter(models.User.uuid == client_uuid).update(
                update_data
            )

        db.commit()
        db.refresh(client)

        return client

    except HTTPException as e:
        db.rollback()
        raise e


def service_provider_rating(rating: schemas.Rating, db: Session):
    try:
        # Validate service provider
        service_provider = (
            db.query(models.User)
            .filter(models.User.uuid == rating.service_provider_uuid)
            .first()
        )
        if not service_provider:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content="Service provider not found",
            )

        # Validate client
        client = (
            db.query(models.User).filter(models.User.uuid == rating.client_uuid).first()
        )
        if not client:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content="Client not found",
            )

        # Calculate average rating from question_answer values
        answer_values = list(rating.question_answer.values())
        numeric_values = [v for v in answer_values if isinstance(v, (int, float))]

        if not numeric_values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No numeric answers provided for rating calculation",
            )

        current_average = sum(numeric_values) / len(numeric_values)

        # Save the new rating
        new_rating = models.Ratings(
            client_uuid=rating.client_uuid,
            service_provider_uuid=rating.service_provider_uuid,
            question_answer=rating.question_answer,
            rated_by="client",
            average_rating=current_average,
        )
        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)

        # Recalculate overall average for the service provider
        ratings_query = (
            db.query(models.Ratings.average_rating)
            .filter(
                models.Ratings.service_provider_uuid == rating.service_provider_uuid,
                models.Ratings.rated_by == "client",
            )
            .all()
        )

        average_ratings_list = [r[0] for r in ratings_query]
        overall_avg_rating = (
            sum(average_ratings_list) / len(average_ratings_list)
            if average_ratings_list
            else 0
        )

        # Update 'rating' field inside 'details' JSONB in User table
        details = service_provider.details or {}
        details.setdefault("service_provider", {})["rating"] = round(
            overall_avg_rating, 2
        )

        db.execute(
            update(models.User)
            .where(models.User.uuid == rating.service_provider_uuid)
            .values(details=details)
        )
        db.commit()

        return {
            "message": "Rating submitted successfully",
            "overall_avg_rating": round(overall_avg_rating, 2),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error occurred",
        ) from e


async def send_request(request_data: schemas.RequestCreate, db: Session):
    try:
        # Fetch users
        client_user = (
            db.query(models.User)
            .filter(models.User.uuid == request_data.client_id)
            .first()
        )
        provider_user = (
            db.query(models.User)
            .filter(models.User.uuid == request_data.provider_id)
            .first()
        )

        if not client_user or not provider_user:
            raise HTTPException(status_code=404, detail="Client or Provider not found")

        # Get client details
        client_details = client_user.details.get("client", {})
        client_first_name = client_details.get("first_name", "Unknown")
        client_last_name = client_details.get("last_name", "Unknown")

        # Save request
        db_request = models.Request(
            id=str(uuid.uuid4()),
            client_id=request_data.client_id,
            provider_id=request_data.provider_id,
        )

        db.add(db_request)
        db.commit()
        db.refresh(db_request)

        # Send notification to service provider
        notification = models.Notification(
            user_id=request_data.provider_id,
            title="New Connection Request",
            message=f"{client_first_name} {client_last_name} has requested to connect with you.",
            is_read=False,
            type="SEND_REQUEST_NOTIFY",
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

        # Send real-time notificatio
        await manager.send_to_user(
            request_data.provider_id,
            f"New Request: {client_first_name} {client_last_name} wants to connect with you.",
        )
        await send_email(
            request_data.provider_id,
            "New Connection Request",
            f"{request_data.client_id} has requested to connect with you",
        )
        return db_request

    except Exception as e:
        logger.log_error(f"{e!s}")
        return JSONResponse(
            status_code=500, content={"message": f"Internal server error: {e!s}"}
        )


def change_assessment(client_uuid: UUID, need: schemas.ChangeAssessment, db: Session):
    # Fetch the existing client
    client = db.query(models.User).filter(models.User.uuid == client_uuid).first()

    if not client:
        return {"error": "Client not found"}

    # Ensure 'client' key exists in details
    if "client" not in client.details:
        client.details["client"] = {}

    # Update only the category_id
    client.details["client"]["primary_need"] = need.primary_need
    client.details["client"]["secondary_need"] = need.secondary_need

    flag_modified(client, "details")

    db.commit()
    db.refresh(client)

    # Query for primary need (single integer)
    primary_need_obj = (
        db.query(models.Category)
        .filter(models.Category.category_id == need.primary_need)
        .first()
    )
    updated_primary_need = primary_need_obj.category_name if primary_need_obj else None

    # Query for secondary need (list of integers)
    secondary_need_objs = (
        db.query(models.Category)
        .filter(models.Category.category_id.in_(need.secondary_need))
        .all()
    )
    updated_secondary_need = [
        obj.category_name for obj in secondary_need_objs
    ]  # Get list of names

    return {
        "message": "Primary need updated successfully",
        "updated_primary_need_id": need.primary_need,
        "updated_primary_need": updated_primary_need,
        "updated_secondary_need_id": need.secondary_need,
        "updated_secondary_need": updated_secondary_need,
    }


def get_client_dashboard(client_uuid: UUID, db: Session):
    client = db.query(models.User).filter(models.User.uuid == client_uuid).first()

    if not client:
        return {"error": "Client not found"}

    total_service_provider = (
        db.query(models.User)
        .filter(models.User.role_type == "service_provider")
        .count()
    )

    category_id = client.details.get("client", {}).get("category_id")

    category_name = None
    if category_id:
        category = (
            db.query(models.Category)
            .filter(models.Category.category_id == category_id)
            .first()
        )
        category_name = category.category_name if category else "Unknown"

    return {"service_provider": total_service_provider, "category": category_name}
