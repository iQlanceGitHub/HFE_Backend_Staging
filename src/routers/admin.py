import json
from typing import Dict
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import UUID4, EmailStr
from sqlalchemy.orm import Session

from src.api import schemas
from src.common import admins, signup_document
from src.configs import database
from src.models import models

get_db = database.get_db

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/sub-admins")
async def add_sub_admin(
    # sub_admin: SubAdminCreate,
    request: Request,
    uuid: UUID = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    useremail: EmailStr = Form(...),
    gender: str = Form("Male"),
    phone: str | None = Form(None),
    password: str = Form(...),
    permission: str = Form("{}"),
    profile_img: UploadFile = File(None),
    header_image: UploadFile = File(None),
    avatar_selection: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        permission_dict = json.loads(permission)  # Convert JSON string to dict
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid permission format")
    subadmin_data = schemas.SubAdminCreate(
        uuid=uuid,
        useremail=useremail,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        phone=phone,
        password=password,
        permission=permission_dict,
        profile_img=profile_img,
        header_image=header_image,
    )

    return await admins.create_sub_admin(
        request, subadmin_data, profile_img, header_image, avatar_selection, db
    )


@router.post("/sub-admins/{sub_admin_uuid}")
async def sub_admin_status(sub_admin_uuid: str, db: Session = Depends(get_db)):
    return await admins.sub_admin_status(sub_admin_uuid, db)


@router.delete("/subadmin/{subadmin_uuid}", response_model=dict)
def delete_sub_admin(
    subadmin_uuid: UUID,
    request: schemas.SoftDeleteRequest,
    db: Session = Depends(get_db),
):
    return admins.soft_delete_subadmin(subadmin_uuid, request, db)


@router.get("/subadmin")
def get_subadmin(subadmin: UUID, db: Session = Depends(get_db)):
    return admins.get_sub_admin(subadmin, db)


@router.get("/sub-all-admins")
async def get_all_subadmins(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    name: str = Query(None),
):
    try:
        return await admins.get_all_subadmins(
            skip=skip, limit=limit, db=db, name_original=name
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/create-question")
def create_question(question: schemas.QuestionCreate, db: Session = Depends(get_db)):
    return admins.create_que(question, db)


@router.patch("/edit-subadmin/{uuid}")
async def edit_subAdmin(
    uuid: UUID,
    request: Request,
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    gender: str | None = Form(None),
    permission: str | None = Form(None),
    updated_by: UUID = Form(...),
    profile_img: UploadFile = File(None),  # Declare file separately
    header_image: UploadFile = File(None),  # Declare file separately
    avatar_selection: str = Form(None),  # Declare form field separately
    useremail: EmailStr | None = Form(None),
    phone: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if permission:
        try:
            permission_data = json.loads(permission)  # Try to parse JSON string
        except json.JSONDecodeError:
            raise ValueError(
                "Invalid JSON format in permission field"
            )  # Provide a clearer error message
    else:
        permission_data = {}
    sub_admin_data = schemas.editSubAdmin(
        updated_by=updated_by,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        permission=permission_data,
        profile_img=profile_img,
        header_image=header_image,
        phone=phone,
        email=useremail
    )
    return await admins.update_subadmin(
        uuid, request,useremail, sub_admin_data, profile_img, header_image, avatar_selection, db
    )


@router.post("/create-subscription", response_model=schemas.SubscriptionResponse)
def create_subscription(
    subscription: schemas.createSubscription, db: Session = Depends(get_db)
):
    return admins.create_subscriptions(subscription, db)


@router.patch(
    "/update-subscription/{subscription_id}",
    response_model=schemas.updateSubscriptionresponse,
)
def update_subscription(
    subscription_id: int,
    updated_subscription: schemas.updateSubscription,
    db: Session = Depends(get_db),
):
    return admins.update_subscription(subscription_id, updated_subscription, db)


@router.get("/get-all-subscription", response_model=schemas.ListofSubscriptionResponse)
async def get_all_subscription(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    name: str = Query(None),
):
    return await admins.get_all_subscriptions(
        skip=skip, limit=limit, db=db, name_original=name
    )


@router.delete("/delete-subscription/{subscription_id}")
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    return admins.delete_subscriptions(subscription_id, db)


@router.post("/category")
async def create_category(
    category: schemas.CategoryCreate, db: Session = Depends(get_db)
):
    return await admins.create_cat(category, db)


@router.post("/subcategory")
async def add_new_subcategory(
    subcategory: schemas.SubCategoryCreate, db: Session = Depends(get_db)
):
    return await admins.create_sub(subcategory, db)


@router.get("/categories/{category_id}/subcategories")
def get_sub_categories(category_id: int, db: Session = Depends(get_db)):
    return admins.get_subcategories(category_id, db)


@router.get("/categories")  # , response_model=schemas.ListofCategoryResponse
async def get_categories(
    skip: int = None,
    limit: int = None,
    db: Session = Depends(get_db),
    name: str = Query(None),
):
    return await admins.get_all_categories(
        skip=skip, limit=limit, db=db, name_original=name
    )


@router.delete("/delete-category/{category_id}")
def delete_category(category_id: int,uuid:UUID = None ,db: Session = Depends(get_db)):
    return admins.delete_category(category_id,uuid,db)


@router.delete("/delete-subCategory/{sub_category_id}")
def delete_subcategory(sub_category_id: int, db: Session = Depends(get_db)):
    return admins.delete_subcategory(sub_category_id, db)


@router.patch("/update-category/{category_id}")
async def update_category(
    category_id: int,
    update_category: schemas.UpdateCategory,
    db: Session = Depends(get_db),
):
    return await admins.edit_category(category_id, update_category, db)


# @router.patch("/update SubCategory/{category_id}")
# def update_subcategory(sub_category_id:int, updated_subcategory: schemas.UpdateSubCategory, db: Session=Depends(get_db)):
#     return admins.update_subcategory(sub_category_id, updated_subcategory, db)


@router.post("/categories/other")
async def create_other_category(
    category_name: str,
    other_category_id: int | None = None,
    db: Session = Depends(get_db),
):
    return await admins.other_category(category_name, other_category_id, db)

@router.post("/sub-categories/other")
async def create_other_category(
    sub_category_name: str,
    category_id: int | None = None,
    db: Session = Depends(get_db),
):
    return await admins.other_sub_category(sub_category_name, category_id, db)


@router.patch("/categories/{category_id}/approve")
def approve_category(category_id: int,uuid: UUID = None, db: Session = Depends(get_db)):
    return admins.approve_category(category_id, uuid,db)


@router.patch("/categories/{category_id}/reject")
def reject_category(category_id: int, uuid: UUID = None,db: Session = Depends(get_db)):
    return admins.reject_category(category_id, db)

@router.patch("/sub-categories")
def update_subcategory(
    data : schemas.UpdateSubcategory,
    db: Session = Depends(get_db),
):
    return admins.update_subcategory(data,db)

@router.get("/approved-categories")
def get_approve_categories(skip:int = None,limit: int = None,db: Session = Depends(get_db)):
    return admins.get_approved_categories(skip,limit,db)


@router.get("/requested-categories")
def get_requested_categories(skip: int = None,limit: int = None,db: Session = Depends(get_db)):
    return admins.get_requested_categories(skip,limit,db)


@router.post("/create-adbanner")
async def create_adbanner(
    request: Request,
    created_by_uuid: str = Form(...),
    alternative_text: str = Form(...),
    category_id: int = Form(...),
    link: str = Form(...),
    image_url: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    adbanner_data = schemas.AdBanner(
        created_by_uuid=created_by_uuid,
        alternative_text=alternative_text,
        category_id=category_id,
        link=link,
    )
    return await admins.create_adbanner(request, adbanner_data, image_url, db)


@router.patch("/update-adbanner/{adbanner_id}")
async def update_adbanner(
    adbanner_id: int,
    request: Request,
    updated_by_uuid: str | None = Form(None),
    alternative_text: str | None = Form(None),
    category_id: int | None = Form(None),
    link: str | None = Form(None),
    image_url: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    updated_adbanner_data = schemas.UpdateAdBanner(
        updated_by_uuid=updated_by_uuid,
        alternative_text=alternative_text,
        category_id=category_id,
        link=link,
        image_url=image_url,
    )
    return await admins.update_adbanner(
        adbanner_id, request, updated_adbanner_data, image_url, db
    )


@router.post("/images/{image_id}")
def status_update_adbanner(adbanner_id: int, db: Session = Depends(get_db)):
    return admins.adbanner_status(adbanner_id, db)


@router.delete("/adbanner-delete/{adbanner_id}")
def delete_adbanner(adbanner_id: int, db: Session = Depends(get_db)):
    return admins.delete_adbanner(adbanner_id, db)


@router.get("/get-all-images")
async def get_all_adbanner(
    skip: int = None,
    limit: int = None,
    db: Session = Depends(get_db),
    alternative_text: str = Query(None),
):
    return await admins.get_all_adbanner(
        skip=skip, limit=limit, db=db, alternative_text_original=alternative_text
    )


@router.post("/broadcasts/")
async def create_broadcast(
    broadcast: schemas.BroadcastMessageCreate, db: Session = Depends(get_db)
):
    created_broadcast = await admins.create_broadcast(broadcast, db)
    recipients = broadcast.recipients

    return created_broadcast


@router.get("/broadcasts/{broadcast_id}", response_model=schemas.BroadcastMessageCreate)
def read_broadcast(broadcast_id: int, db: Session = Depends(get_db)):
    return admins.read_broadcast(broadcast_id, db)


@router.get("/all-broadcasts")
async def read_all_broadcast(
    user_id: UUID4,
    skip: int = None,
    limit: int = None,
    db: Session = Depends(get_db),
    title: str = Query(None),
):
    return await admins.get_all_broadcast(user_id, skip, limit, db, title)


@router.delete("/delete-broadcast/{broadcast_id}")
def delete_broadcast(broadcast_id: int, db: Session = Depends(get_db)):
    return admins.delete_broadcast(broadcast_id, db)


@router.post("/create-admin", response_model=schemas.AdminResponse)
async def create_admin(admin: schemas.Admin, db: Session = Depends(get_db)):
    return await admins.create_admin(admin, db)


@router.get("/download-revenue-report", response_class=Response)
def download_report(db: Session = Depends(get_db)):
    """API endpoint to generate and download revenue report"""
    return admins.generate_report(db)


@router.post("/add-rating-question")
async def add_rating_question(
    question: schemas.RatingQuestion, db: Session = Depends(get_db)
):
    return await admins.add_rating_question(question, db)


@router.patch("/update-rating-question")
async def update_rating_question(
    question: schemas.UpdateRatingQuestion, db: Session = Depends(get_db)
):
    return await admins.update_rating_question(question, db)


@router.delete("/delete-rating-question")
def delete_rating_question(
    question_id: int, deleted_by: UUID4, db: Session = Depends(get_db)
):
    return admins.delete_rating_question(question_id, deleted_by, db)


@router.get("/get-rating-question")
async def get_rating_question(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    target_user: str = Query(None),
    question_text: str = Query(None),
):
    return await admins.get_rating_question(
        skip=skip,
        limit=limit,
        db=db,
        target_user=target_user,
        question_text_original=question_text,
    )


@router.get("/questionnaires")
async def get_questionnaires(db: Session = Depends(get_db)):
    return await admins.get_all_questionnaires(db)


@router.post("/questionnaires")
async def get_questionnaires(data: Dict = Body(...), db: Session = Depends(get_db)):
    return await admins.add_questionnaires(data, db)


@router.delete("/questionnaires")
async def delete_questionnaires(db: Session = Depends(get_db)):
    return await admins.delete_questionnaires(db)


@router.put("/questionnaires")
async def update_questionnaires(data: Dict = Body(...), db: Session = Depends(get_db)):
    return await admins.update_questionnaires(data, db)


@router.post("/create_sigup_doc", response_model=schemas.SignUpDocumentBase)
def create_doc(document: schemas.SignUpDocumentCreate, db: Session = Depends(get_db)):
    return signup_document.create_document(db=db, document=document)


@router.get("/get_signup_doc")
def read_doc(doc_type: str, db: Session = Depends(get_db)):
    db_doc = signup_document.get_document(db, doc_type=doc_type)
    return db_doc if db_doc else {}


@router.put("/update_signup_doc", response_model=schemas.SignUpDocumentBase)
def update_doc(
    doc_type: str, document: schemas.SignUpDocumentCreate, db: Session = Depends(get_db)
):
    db_doc = signup_document.update_document(db, doc_type=doc_type, document=document)
    if db_doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return db_doc


@router.get("/get-all-titanium")
def getalltitanium(db: Session = Depends(get_db)):
    titanium_obj = db.query(models.Titanium).all()
    if titanium_obj is None:
        return {"status": 200, "message": "No Titanium plan found"}

    data = []
    for titanium in titanium_obj:
        user_obj = (
            db.query(models.User).filter(models.User.uuid == titanium.uuid).first()
        )
        data.append(
            {
                "uuid": titanium.uuid,
                "name": user_obj.details["service_provider"]["name"],
                "communication": titanium.view_other_client,
                "client_count": titanium.clients_count,
                "price": f"{titanium.payment_price}/{titanium.duration}",
                "subscription_id": "",
                "status": titanium.status,
            }
        )
    return {"status": 200, "data": data, "count": len(data)}

@router.get("/total-counts")
def get_total_counts(uuid:UUID = None,db: Session = Depends(get_db)):


    total_service_providers = db.query(models.User).filter(models.User.role_type == "service_provider").count()
    if uuid:
        staff_count = db.query(models.User).filter(models.User.created_by == uuid,models.User.role_type == "staff").count()
        return {
            "staff":staff_count,
            "service_providers": total_service_providers
        }
    
    # All counts
    total_clients = db.query(models.User).filter(models.User.role_type == "client").count()
    total_subadmins = db.query(models.User).filter(models.User.role_type == "sub_admin").count()
    
    # Active counts
    total_active_service_providers = db.query(models.User).filter(models.User.role_type == "service_provider", models.User.is_activated == True).count()
    total_active_clients = db.query(models.User).filter(models.User.role_type == "client", models.User.is_activated == True).count()
    total_active_subadmins = db.query(models.User).filter(models.User.role_type == "sub_admin", models.User.is_activated == True).count()
    
    # Inactive counts
    total_inactive_service_providers = db.query(models.User).filter(models.User.role_type == "service_provider", models.User.is_activated == False).count()
    total_inactive_clients = db.query(models.User).filter(models.User.role_type == "client", models.User.is_activated == False).count()
    total_inactive_subadmins = db.query(models.User).filter(models.User.role_type == "sub_admin", models.User.is_activated == False).count()
    
    # prospective clients
    # total_prospective_clients = db.query(models.User).filter(models.User.user_type == "client", models.User.is_prospective == True).count()
    
    
    return {
        "service_providers": {
            "total": total_service_providers,
            "active": total_active_service_providers,
            "inactive": total_inactive_service_providers,
        },
        "clients": {
            "total": total_clients,
            "active": total_active_clients,
            "inactive": total_inactive_clients,
        },
        "subadmins": {
            "total": total_subadmins,
            "active": total_active_subadmins,
            "inactive": total_inactive_subadmins,
        }
    }

@router.post("/faqs")
def create_faq(
    faq: schemas.FAQCreate, db: Session = Depends(get_db)
):
    return  admins.create_faq(faq, db)

@router.get("/faqs")
def get_faqs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    role_type: str = Query(None),
    db: Session = Depends(get_db)
):
    return admins.get_faqs(skip, limit, db, role_type)

@router.patch("/faqs/{faq_id}")
def update_faq(
    faq_id: int,
    faq: schemas.FAQUpdate,
    db: Session = Depends(get_db)
):
    return admins.update_faq(faq_id, faq, db)

@router.delete("/faqs/{faq_id}")
def delete_faq(
    faq_id: int,
    db: Session = Depends(get_db)
):
    return admins.delete_faq(faq_id, db)

@router.get("/organization-type")
def get_organization_type(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db)
):
    return admins.get_organization_type(skip,limit,db)

@router.post("/organization-type")
def create_organization_type(
    organization_type: schemas.OrganizationTypeCreate, db: Session = Depends(get_db)
):
    return admins.create_organization_type(organization_type, db)

@router.patch("/organization-type/{organization_type_id}")
def update_organization_type(
    organization_type_id: int,
    organization_type: schemas.OrganizationTypeUpdate,
    db: Session = Depends(get_db)
):
    return admins.update_organization_type(organization_type_id, organization_type, db)

@router.delete("/organization-type/{organization_type_id}")
def delete_organization_type(
    organization_type_id: int, db: Session = Depends(get_db)
):
    return admins.delete_organization_type(organization_type_id, db)

@router.post("/site-settings")
def create_site_settings(
    site_settings: schemas.SiteSettingsCreate, db: Session = Depends(get_db)
):
    return admins.create_site_settings(site_settings, db)

@router.get("/site-settings")
def get_site_settings(
    db: Session = Depends(get_db)
):
    return admins.get_site_settings(db)

@router.patch("/site-settings")
def update_site_settings(
    site_settings: schemas.SiteSettingsCreate, db: Session = Depends(get_db)
):
    return admins.update_site_settings(site_settings, db)

@router.delete("/site-settings")
def delete_site_settings(
    db: Session = Depends(get_db)
):
    return admins.delete_site_settings(db)
@router.get("/export/download")
def export_data(
    db: Session = Depends(get_db),
    id: UUID4 | None = Query(None),
):
    return admins.export_data(db, id)