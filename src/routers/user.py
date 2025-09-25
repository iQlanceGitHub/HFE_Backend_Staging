import asyncio
from uuid import UUID
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import UUID4, BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy.sql import not_
import json
from src.api import schemas
from src.api.schemas import (
    ClientCreate,
    ServiceProviderCreate,
    ServiceProviderResponse,
    AdminUpdateServiceProvider
)
from src.models import models
from src.common.email_service import send_email
from src.common import user
from src.common.translate import translate_fields_to_spanish
from src.configs import database
from src.configs.config import logger
from src.common.tasks import redis_app

get_db = database.get_db


class Titanium(BaseModel):
    current_user: UUID4


router = APIRouter(prefix="/users", tags=["Users"])


@router.post(
    "/login",
)
def login(request: schemas.Login = Depends(), db: Session = Depends(get_db)):
    return user.login_info(request, db)


@router.post("/forgot-password")
def forgot_password(email: str, db: Session = Depends(get_db)):
    return asyncio.run(user.forgot_password(email, db))


@router.post("/verify-otp")
def verify_otp(email: str, otp: str, db: Session = Depends(get_db)):
    return asyncio.run(user.verify_otp(email, otp, db))


@router.post("/reset-password")
def reset_password(OTP: str, new_password: str, db: Session = Depends(get_db)):
    return user.reset_password(OTP, new_password, db)


@router.post("/service-provider", response_model=ServiceProviderResponse)
def create_service_provider(
    service_provider: ServiceProviderCreate, db: Session = Depends(get_db)
):
    return asyncio.run(user.create_service_provider(service_provider, db))


@router.get("/all-service-providers")
def get_all_service_providers(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    name: str = Query(None),
    client_uuid: str = Query(None),
    favourite: bool = Query(None),
    blocked: bool = Query(None),
    estimated_clients: str = Query(None),
    organization_type: str = Query(None),
    county: str = Query(None),
    city: str = Query(None),
    zipcode: int = Query(None),
    category: int = Query(None),
    sub_category: int = Query(None),
    status: str = Query(None),
    is_activated: bool = Query(None),
    sort_by: str = Query(None),
    sort_order: str = Query("asc"),
    old_new: str = Query(None),
    primary_need=Query(None),
    secondary_need: str | None = Query(None),
    role_type: str = Query(None),
    region: str | None = Query(None),
):
    return asyncio.run(
        user.get_all_service_providers(
            skip=skip,
            limit=limit,
            db=db,
            name_original=name,
            client_uuid=client_uuid,
            favourite=favourite,
            blocked=blocked,
            estimated_clients=estimated_clients,
            organization_type_original=organization_type,
            country_original=county,
            city_original=city,
            zipcode=zipcode,
            category=category,
            sub_category=sub_category,
            status=status,
            is_activated=is_activated,
            sort_by=sort_by,
            sort_order=sort_order,
            old_new=old_new,
            primary_need=primary_need,
            secondary_need=secondary_need,
            role_type=role_type,
            region=region,
        )
    )


@router.get("/service-provider")
def get_service_providers(service_provider_uuid: UUID, db: Session = Depends(get_db)):
    return user.get_service_provider(service_provider_uuid, db)


@router.patch(
    "/service-provider/{uuid}", response_model=schemas.UpdateServiceProviderResponse
)
def update_service_provider(
    request: Request,
    uuid: UUID,
    admin_uuid: UUID4 = Form(...),
    categories: str | None = Form(None),
    # Flattened serviceProviderDetails fields as form-data
    name: str | None = Form(None),
    estimated_clients: int | None = Form(None),
    organization_type: str | None = Form(None),
    tax_id: str | None = Form(None),
    contact_title: str | None = Form(None),
    contact_name: str | None = Form(None),
    contact_email: str | None = Form(None),
    founder_first_name: str | None = Form(None),
    founder_last_name: str | None = Form(None),
    address_1: str | None = Form(None),
    address_2: str | None = Form(None),
    county: str | None = Form(None),
    city: str | None = Form(None),
    country: str | None = Form(None),
    state: str | None = Form(None),
    zip_code: str | None = Form(None),
    region: str | None = Form(None),
    lat: float | None = Form(None),
    long: float | None = Form(None),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    gender: str | None = Form(None),
    socialmedia_links: str | None = Form(None),
    website_link: str | None = Form(None),
    question: str | None = Form(None),
    category_id: int | None = Form(None),
    sub_category_id: int | None = Form(None),
    description: str | None = Form(None),
    brochure: UploadFile | str | None = File(None),
    rating: float | None = Form(None),
    client_count: int | None = Form(None),
    subscription: str | None = Form(None),
    staff_first_name: str | None = Form(None),
    staff_last_name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    # Prepare social media links list
    social_links_list = None
    if socialmedia_links is not None:
        try:
            social_links_list = json.loads(socialmedia_links)
        except Exception:
            social_links_list = [s.strip() for s in socialmedia_links.split(",")] if socialmedia_links else []

    # Use only flattened fields
    merged: dict = {}
    for key, value in {
        "name": name,
        "estimated_clients": estimated_clients,
        "organization_type": organization_type,
        "tax_id": tax_id,
        "contact_title": contact_title,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "founder_first_name": founder_first_name,
        "founder_last_name": founder_last_name,
        "address_1": address_1,
        "address_2": address_2,
        "county": county,
        "city": city,
        "country": country,
        "state": state,
        "zip_code": zip_code,
        "region": region,
        "lat": lat,
        "long": long,
        "phone": phone,
        "email": email,
        "gender": gender,
        # socialmedia_links handled separately
        "website_link": website_link,
        "question": question,
        "category_id": category_id,
        "sub_category_id": sub_category_id,
        "description": description,
        "brochure": brochure,
        "rating": rating,
        "client_count": client_count,
        "subscription": subscription,
        "staff_first_name": staff_first_name,
        "staff_last_name": staff_last_name,
    }.items():
        if value is not None:
            merged[key] = value

    if social_links_list is not None:
        merged["socialmedia_links"] = social_links_list

    payload: AdminUpdateServiceProvider = AdminUpdateServiceProvider(
        admin_uuid=admin_uuid,
        categories=categories,
        **merged,
    )
    return asyncio.run(user.update_service_provider(uuid, request, payload, brochure, db))


@router.post("/service-provider/{uuid}")
def status_service_provider(uuid: UUID4, db: Session = Depends(get_db)):
    return asyncio.run(user.status_service_provider(uuid, db))


@router.delete("/service-provider/{uuid}")
def delete_service_provider(
    uuid: UUID4,
    admin_uuid: schemas.SoftDeleteServiceProvider,
    db: Session = Depends(get_db),
):
    return user.delete_service_provider(uuid, admin_uuid, db)


@router.put("/provider/status/{service_provider_uuid}")
def update_status(
    service_provider_uuid: UUID,
    status_update: schemas.StatusUpdate,
    db: Session = Depends(get_db),
):
    return asyncio.run(
        user.update_provider_status(service_provider_uuid, status_update, db)
    )


@router.get("/avatar")
def get_avatar():
    return user.get_avatars()


@router.post("/client")
async def create_client(
    request: Request,
    admin_uuid: UUID4 = Form(...),
    useremail: EmailStr = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    dob: str | None = Form(None),
    ssn: str | None = Form(None),
    gender: str = Form("Male"),
    address_1: str = Form(...),
    address_2: str | None = Form(None),
    city: str = Form(...),
    county: str = Form(None),
    state: str = Form(...),
    zip_code: str = Form(...),
    region: str = Form(None),
    lat: str = Form(None),
    long: str = Form(None),
    phone: str | None = Form(None),
    website_link: str | None = Form(None),
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    avatar_selection: str | None = Form(None),
    db: Session = Depends(get_db),
):
    client_data = ClientCreate(
        admin_uuid=admin_uuid,
        useremail=useremail,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        ssn=ssn,
        gender=gender,
        address_1=address_1,
        address_2=address_2,
        city=city,
        county=county,
        state=state,
        zip_code=zip_code,
        region=region,
        lat=lat,
        long=long,
        phone=phone,
        website_link=website_link,
    )
    return await user.create_client(
        request, client_data, profile_img, header_img, avatar_selection, db
    )


@router.get("/all-client", response_model=schemas.ListofClientResponse)
def get_all_client(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    name: str = Query(None),
    is_activated: bool = Query(None),
    user_id: UUID = Query(None),
    old_new: str = Query(None),
    zipcode: int = Query(None),
    county: str = Query(None),
    city: str = Query(None),
    category: int = Query(None),
    sort_order: str = Query("asc"),
):
    return asyncio.run(
        user.get_all_client(
            skip=skip,
            limit=limit,
            db=db,
            name_original=name,
            is_activated=is_activated,
            user_id=user_id,
            old_new=old_new,
            zipcode=zipcode,
            county=county,
            city=city,
            category=category,
            sort_order=sort_order,
        )
    )


@router.get("/all-other-client", response_model=schemas.ListofClientResponse)
def get_all_other_client(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    name: str = Query(None),
    is_activated: bool = Query(None),
    user_id: UUID = Query(None),
    old_new: str = Query(None),
    zipcode: int = Query(None),
    county: str = Query(None),
    city: str = Query(None),
    category: int = Query(None),
    sort_order: str = Query("asc"),
):
    return asyncio.run(
        user.get_all_client(
            skip=skip,
            limit=limit,
            db=db,
            name_original=name,
            is_activated=is_activated,
            user_id=user_id,
            old_new=old_new,
            zipcode=zipcode,
            county=county,
            city=city,
            category=category,
            sort_order=sort_order,
            is_other_client=True,
        )
    )


@router.get("/client")
def get_client(client_uuid: UUID, db: Session = Depends(get_db)):
    return user.get_client(client_uuid, db)


@router.patch("/client/{client_uuid}", response_model=schemas.UpdateClientResponse)
async def update_client(
    request: Request,
    client_uuid: UUID4,
    admin_uuid: str | None = Form(None),
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    dob: str | None = Form(None),
    ssn: str | None = Form(None),
    gender: str | None = Form("Male"),
    address_1: str | None = Form(None),
    address_2: str | None = Form(None),
    city: str | None = Form(None),
    county: str | None = Form(None),
    state: str | None = Form(None),
    zip_code: str | None = Form(None),
    region: str | None = Form(None),
    lat: str | None = Form(None),
    long: str | None = Form(None),
    website_link: str | None = Form(None),
    housing_situation: str | None = Form(None),
    Question: str | None = Form(None),
    socialmedia_links: str | None = Form(None),
    country: str | None = Form(None),
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    avatar_selection: str | None = Form(None),
    useremail: EmailStr | None = Form(None),
    phone: str | None = Form(None),
    resume: UploadFile | str | None = File(None),
    db: Session = Depends(get_db),
):
    if isinstance(resume, str) and (resume == "null" or resume.strip() == ""):
        resume = None

    client_data = schemas.UpdateClient(
        admin_uuid=admin_uuid,
        client_uuid=client_uuid,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        ssn=ssn,
        gender=gender,
        address_1=address_1,
        address_2=address_2,
        city=city,
        county=county,
        state=state,
        zip_code=zip_code,
        region=region,
        lat=lat,
        long=long,
        website_link=website_link,
        housing_situation=housing_situation,
        Question=Question,
        socialmedia_links=socialmedia_links.split(",") if socialmedia_links else None,
        country=country,
        useremail=useremail,
        phone=phone,
    )
    return await user.update_client(
        request,
        client_uuid,
        useremail,
        client_data,
        profile_img,
        header_img,
        avatar_selection,
        resume,
        db,
    )


@router.delete("/client/{uuid}")
def delete_client(
    uuid: UUID4, deleted_by: schemas.SoftDeleteClient, db: Session = Depends(get_db)
):
    return user.delete_client(uuid, deleted_by, db)


@router.post("/client/{uuid}")
def status_client(uuid: UUID4, db: Session = Depends(get_db)):
    return user.status_client(uuid, db)


# @router.post("/client/resume-upload")
# def resume_upload(create_resume: ResumeUploadBase, db: Session = Depends(get_db)):
#     return user.create_resume_upload(create_resume, db)


# @router.post("/create-notification", response_model=schemas.createNotification)
# def Create_Notification(
#     notification: schemas.createNotification, db: Session = Depends(get_db)
# ):
#     return user.create_notification(notification, db)


# @router.get("/show-notification/{service_provider_id}")
# def Show_Notification(service_provider_id: int, db: Session = Depends(get_db)):
#     return user.show_notification(service_provider_id, db)


# @router.post("/create-question-type")
# def create_question_type(
#     question_type: schemas.QuestionType, db: Session = Depends(get_db)
# ):
#     return user.create_question_type(question_type, db)


# @router.post("/create-question")
# def create_question(
#     question_data: schemas.QuestionCreate, db: Session = Depends(get_db)
# ):
#     return user.create_question(question_data, db)


# @router.patch("/update-question")
# def update_question(
#     question_data: schemas.QuestionUpdate,
#     admin_uuid: UUID4,
#     db: Session = Depends(get_db),
# ):
#     return user.update_question(question_data, admin_uuid, db)


# @router.delete("/delete-question/{question_id}")
# def delete_question(
#     question_data: schemas.QuestionDelete,
#     admin_uuid: UUID4,
#     db: Session = Depends(get_db),
# ):
#     return user.delete_question(question_data, admin_uuid, db)


@router.get("/get-all-question")
def get_all_question(
    skip: int = Query(None), limit: int = Query(None), db: Session = Depends(get_db)
):
    return user.get_all_questions(skip=skip, limit=limit, db=db)


@router.get("/get-question")
def get_question(question_id: int, db: Session = Depends(get_db)):
    return user.get_question(question_id, db)


@router.post("/favorite-user")
def favorite_user(fav_user: schemas.FavoriteUser, db: Session = Depends(get_db)):
    return user.favorite_user(fav_user, db)


@router.post("/block-user")
def block_user(block_user: schemas.BlockedUser, db: Session = Depends(get_db)):
    return user.block_user(block_user, db)


@router.get("/user-list")
def get_favourite_blocked_users(
    user_uuid: UUID, type: str, db: Session = Depends(get_db)
):
    return user.get_favourite_blocked_users(user_uuid, type, db)


@router.post("/client-upload")
async def bulk_upload_clients(
    admin_uuid: UUID, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    return await user.bulk_client_upload(admin_uuid, file, db)


@router.post("/service-provider-upload")
async def bulk_upload_service_provider(
    admin_uuid: UUID, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    return await user.bulk_service_provider_upload(admin_uuid, file, db)


@router.post("/categoty-upload")
async def bulk_upload_category(
    admin_uuid: UUID, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    return await user.bulk_upload_categories(admin_uuid, file, db)


@router.get("/export-clients")
async def export_clients(
    format: str = Query("csv", enum=["csv", "excel"]),
    language: str = Query(None),
    db: Session = Depends(get_db),
):
    fields_to_translate = [
        "first_name",
        "last_name",
        "gender",
        "housing_situation",
        "address_1",
        "address_2",
        "city",
        "county",
        "state",
        "zip_code",
        "comments",
        "Question",
        "question",
        "category_name",
    ]

    """Exports client data in CSV or Excel format based on user choice."""
    data = user.generate_client_data(db)

    if not data:
        return {"message": "No client data available"}

    if language == "es":
        data = [
            await translate_fields_to_spanish(row, fields_to_translate) for row in data
        ]

    if format == "csv":
        csv_file = user.generate_csv(data)
        response = StreamingResponse(csv_file, media_type="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=clients.csv"
    else:
        excel_file = user.generate_excel(data)
        response = StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response.headers["Content-Disposition"] = "attachment; filename=clients.xlsx"

    return response


@router.get("/export-service-providers")
async def export_service_providers(
    format: str = Query("csv", enum=["csv", "excel"]),
    language: str = Query(None),
    db: Session = Depends(get_db),
):
    fields_to_translate = [
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
        "description",
        "comments",
        "staff_first_name",
        "staff_last_name",
    ]

    """Export service providers as CSV or Excel."""

    if language == "es":
        data = [
            await translate_fields_to_spanish(row, fields_to_translate) for row in data
        ]

    if format == "excel":
        file_output = user.generate_service_provider_excel(db)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        file_ext = "xlsx"
    else:
        file_output = user.generate_service_provider_csv(db)
        media_type = "text/csv"
        file_ext = "csv"

    response = StreamingResponse(file_output, media_type=media_type)
    response.headers["Content-Disposition"] = (
        f"attachment; filename=service_providers.{file_ext}"
    )
    return response


@router.get("/export-categories")
def export_categories(db: Session = Depends(get_db)):
    csv_file = user.generate_category_csv(db)
    response = StreamingResponse(csv_file, media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=categories.csv"
    return response


@router.patch("/change-password")
def change_password(
    uuid: UUID, current_password: str, new_password: str, db: Session = Depends(get_db)
):
    return user.change_password(uuid, current_password, new_password, db)


@router.post("/email-validation")
def email_validation(useremail: EmailStr, db: Session = Depends(get_db)):
    return user.email_validation(useremail, db)


@router.get("/overview-dashboard")
def get_overview_dashboard(db: Session = Depends(get_db)):
    return user.get_overview_dashboard(db)


@router.post("/titanium")
async def send_titanium_mail(
    data: Titanium,
    db: Session = Depends(get_db),
):
    return await user.send_titanium_mail(data, db)


@router.post("/contact-us")
async def send_contact_us_mail(data: schemas.ContactUs):
    return await user.send_contact_us_mail(data)


@router.post("/send-otp")
async def send_otp(email: EmailStr, user_type: str, db: Session = Depends(get_db)):
    # logger.log_info(f"User claim in progress for the email : {email}")

    user = db.query(models.User).filter(models.User.useremail == email).first()

    # if not user:
    #     # logger.log_warning(
    #     #     f"Password reset attempt for non-existent email {email} "
    #     # )
    #     return {
    #         "status_code":404,
    #         "message": "User not found"
    #     }
    otp = str(random.randint(100000, 999999))

    if user:
        if user.is_deleted and user_type != "newuser":
            logger.log_warning(f"Password reset attempt for deleted user {email} ")
            return {"status_code": 403, "message": "User is deleted"}

        user.password_reset_token = otp
        user.password_reset_expires = datetime.now() + timedelta(minutes=30)

        db.commit()
        db.refresh(user)
    redis_app.setex(f"otp:{email}", 300, otp)

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
                    Thank you for choosing HFE. Use the following OTP to complete your Claim up procedures. OTP is valid for 5 minutes.
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
    # logger.log_info(f"Password reset token saved successfully for email {email} ")
    await send_email(email, "Email verification Otp", body)

    return {"status_code": 200, "message": "OTP sent successfully"}


@router.get("/claim-account")
def get_claim_amount(tax_id: str,organization_name: str, db: Session = Depends(get_db)):
    get_user_obj = (
        db.query(models.User)
        .filter(
            models.User.details["service_provider"]["tax_id"].astext == tax_id,
            models.User.role_type == "service_provider",
            # models.User.is_claimed == False,
            # models.User.is_imported == True,
            models.User.details["service_provider"]["name"].astext.ilike(f"%{organization_name}%"),
        )
        .first()
    )
    # print(type(get_user_obj.details))
    # print("get_user_obj",get_user_obj.details['service_provider'])
    if get_user_obj is None :
        return {"message":"Your Organization name / Tax Id number does not match anything in our system. Please continue entering your information to set up your account"}
    if get_user_obj.is_claimed == True and get_user_obj.is_imported == True:
        return {"message":"This account has already been claimed. Please contact your Administrator for access or email cs@hopeforeverybody.org for assistance."}
    if get_user_obj.is_claimed == False and get_user_obj.is_imported == True:
        return get_user_obj.details["service_provider"] | {"uuid": get_user_obj.uuid}
    

    
    return True


@router.get("/import-history/{uuid}")
def get_import_history(
    uuid: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user_obj = db.query(models.User).filter(models.User.uuid == uuid).first()

    if not user_obj:
        return {"status_code": 404, "message": "User not found"}
    if user_obj.is_deleted:
        return {"status_code": 403, "message": "User is deleted"}

    base_query = db.query(models.ExportData).filter(
        models.ExportData.uploaded_by == uuid
    )
    total = base_query.count()
    results = base_query.offset(skip).limit(limit).all()

    return {"status_code": 200, "data": results, "total": total}


@router.get("/download-imported-file/{id}")
def download_imported_file(
    id: int, uuid: UUID, download_type: str, db: Session = Depends(get_db)
):
    user_obj = db.query(models.User).filter(models.User.uuid == uuid).first()

    if not user_obj:
        return {"status_code": 404, "message": "User not found"}
    if user_obj.is_deleted:
        return {"status_code": 403, "message": "User is deleted"}

    return user.download_imported_file(id, download_type, db)
