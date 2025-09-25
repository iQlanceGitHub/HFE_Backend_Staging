import asyncio
import json
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import EmailStr
from sqlalchemy.orm import Session

from src.api import schemas
from src.api.schemas import (
    CreateServiceProvider,
    UpdateServiceProvider,
)
from src.common import provider
from src.configs import database

get_db = database.get_db


router = APIRouter(prefix="/provider", tags=["Providers"])


@router.post("/service-provider")
async def create_service_provider_self(
    request: Request,
    name: str = Form(None),
    # service_provider_type: str = Form(None),
    estimated_clients: str = Form(...),
    tax_id: str = Form(...),
    organization_type: str = Form(...),
    contact_title: str = Form(None),
    contact_name: str = Form(...),
    contact_email: str = Form(...),
    founder_first_name: str = Form(None),
    founder_last_name: str = Form(None),
    address_1: str = Form(...),
    address_2: str = Form(None),
    county: str = Form(None),
    city: str = Form(...),
    state: str = Form(...),
    country: str = Form(None),
    zip_code: str = Form(None),
    region: str = Form(None, example="region1_texas"),
    lat: str = Form(None),
    long: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    gender: str = Form(None),
    socialmedia_links: str = Form(None),
    website_link: str = Form(None),
    question: str = Form(...),
    description: str = Form(...),
    password: str = Form(...),
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    brochure: UploadFile = File(None),
    categories: str = Form(...),
    db: Session = Depends(get_db),
    keywords: str = Form(None),
):
    socialmedia_links_list = (
        [link.strip() for link in socialmedia_links.split(",")]
        if socialmedia_links
        else []
    )

    keywords_list = []
    if keywords:
        try:
            keywords_list = json.loads(keywords)
        except json.JSONDecodeError:
            keywords_list = [k.strip() for k in keywords.split(",") if k.strip()]

    provider_data = CreateServiceProvider(
        name=name,
        # service_provider_type=service_provider_type,
        estimated_clients=estimated_clients,
        tax_id=tax_id,
        organization_type=organization_type,
        contact_title=contact_title,
        contact_name=contact_name,
        contact_email=contact_email,
        founder_first_name=founder_first_name,
        founder_last_name=founder_last_name,
        address_1=address_1,
        address_2=address_2,
        county=county,
        city=city,
        state=state,
        country=country,
        zip_code=zip_code,
        region=region,
        lat=lat,
        long=long,
        phone=phone,
        email=email,
        gender=gender,
        socialmedia_links=socialmedia_links_list,
        website_link=website_link,
        question=question,
        description=description,
        password=password,
        categories=categories,
        keywords=keywords_list,
    )
    new_provider = await provider.create_service_provder_self(
        request, provider_data, profile_img, header_img, brochure, db
    )
    return new_provider


# @router.get("/service-provider")
# def get_service_provider_self(provider_uuid: UUID, db: Session = Depends(get_db)):
#     return provider.get_service_provider_self(provider_uuid, db)


@router.patch("/service-provider/{uuid}")
def update_service_provider_self(
    uuid: UUID,
    request: Request,
    updated_by: UUID,
    name: str = Form(None),
    # service_provider_type: str = Form(None),
    estimated_clients: str = Form(None),
    tax_id: str = Form(None),
    organization_type: str = Form(None),
    contact_title: str = Form(None),
    contact_name: str = Form(None),
    contact_email: str = Form(None),
    founder_first_name: str = Form(None),
    founder_last_name: str = Form(None),
    address_1: str = Form(None),
    address_2: str = Form(None),
    county: str = Form(None),
    city: str = Form(None),
    state: str = Form(None),
    country: str = Form(None),
    zip_code: str = Form(None),
    region: str = Form(None),
    lat: str = Form(None),
    long: str = Form(None),
    phone: str = Form(None),
    email: str = Form(None),
    socialmedia_links: str = Form(None),
    website_link: str = Form(None),
    question: str = Form(None),
    description: str = Form(None),
    password: str = Form(None),
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    brochure: UploadFile | str | None = File(None),
    categories: str = Form(None),
    keywords: str = Form(None),
    db: Session = Depends(get_db),
):
    try:
        socialmedia_links_list = (
            json.loads(socialmedia_links) if socialmedia_links else []
        )
    except json.JSONDecodeError:
        socialmedia_links_list = (
            [link.strip() for link in socialmedia_links.split(",")]
            if socialmedia_links
            else []
        )

    if isinstance(brochure, str) and (brochure == "null" or brochure.strip() == ""):
        brochure = None

    # Parse keywords from JSON string to list
    keywords_list = []
    if keywords:
        try:
            keywords_list = json.loads(keywords)
        except json.JSONDecodeError:
            keywords_list = [k.strip() for k in keywords.split(",") if k.strip()]

    updated_provider_data = UpdateServiceProvider(
        updated_by=updated_by,
        name=name,
        # service_provider_type=service_provider_type,
        estimated_clients=estimated_clients,
        tax_id=tax_id,
        organization_type=organization_type,
        contact_title=contact_title,
        contact_name=contact_name,
        contact_email=contact_email,
        founder_first_name=founder_first_name,
        founder_last_name=founder_last_name,
        address_1=address_1,
        address_2=address_2,
        county=county,
        city=city,
        state=state,
        country=country,
        zip_code=zip_code,
        region=region,
        lat=lat,
        long=long,
        phone=phone,
        email=email,
        socialmedia_links=socialmedia_links_list,
        website_link=website_link,
        question=question,
        description=description,
        password=password,
        categories=categories,
        keywords=keywords_list,
    )
    return asyncio.run(
        provider.update_service_provider_self(
            uuid, request,email, updated_provider_data, profile_img, header_img, brochure, db
        )
    )


@router.post("/staff")
def add_servive_provider_staff(
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
    subadmin_data = schemas.ProviderStaff(
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

    return asyncio.run(
        provider.create_staff(
            request, subadmin_data, profile_img, header_image, avatar_selection, db
        )
    )


@router.get("/all-provider-staff")
def get_all_staff(
    skip: int = Query(None),
    limit: int = Query(None),
    db: Session = Depends(get_db),
    name: str = Query(None),
    created_by: UUID = None,
):
    try:
        return asyncio.run(
            provider.get_all_staff(
                skip=skip, limit=limit, db=db, name_original=name, created_by=created_by
            )
        )
    except Exception as e:
        return JSONResponse(status_code=500, content=str(e))


@router.get("/provider-staff/{staff_uuid}")
def get_provider_staff(staff_uuid: UUID, db: Session = Depends(get_db)):
    return provider.get_provider_staff(staff_uuid, db)


@router.post("/staff/{staff_uuid}")
async def staff_status(staff_uuid: str, db: Session = Depends(get_db)):
    return await provider.staff_status(staff_uuid, db)


@router.patch("/edit-provider-staff/{uuid}")
def edit_staff(
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
    staff_data = schemas.editProviderStaff(
        updated_by=updated_by,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        permission=permission_data,
        profile_img=profile_img,
        header_image=header_image,
        useremail=useremail,
        phone=phone,
    )
    return asyncio.run(
        provider.update_staff(
            uuid, request,useremail, staff_data, profile_img, header_image, avatar_selection, db
        )
    )


@router.delete("/staff/{staff_uuid}", response_model=dict)
def delete_provider_staff(
    staff_uuid: UUID, request: schemas.SoftDeleteRequest, db: Session = Depends(get_db)
):
    return provider.soft_delete_staff(staff_uuid, request, db)


@router.post("/client-rating")
def create_client_rating(rating: schemas.Rating, db: Session = Depends(get_db)):
    return provider.client_rating(rating, db)


@router.get("/get-subscription/{service_provider_uuid}")
def get_subscription(service_provider_uuid: UUID, db: Session = Depends(get_db)):
    return provider.get_subscription(service_provider_uuid, db)


@router.get("/get_permissions/{service_provider_uuid}")
def get_subscription(service_provider_uuid: UUID, db: Session = Depends(get_db)):
    return provider.get_permissions(service_provider_uuid, db)


@router.post("/add-subscription/{service_provider_uuid}")
def add_subscription(
    service_provider_uuid: UUID,
    subscription: schemas.AddSubscription,
    db: Session = Depends(get_db),
):
    return provider.add_subscription(service_provider_uuid, subscription, db)


# @router.post("/process-renewals")
# def process_renewals(db: Session = Depends(get_db)):
#     provider.process_subscription_renewals(db)
#     return {"message": "Subscription renewals processed successfully"}


@router.get("/request-details")
async def get_request_details_route(
    skip: int = Query(None),
    limit: int = Query(None),
    provider_id: UUID | None = Query(None),
    client_id: UUID | None = Query(None),
    status: str | None = Query(
        None,
        description="Filter by request status. For example: approved, rejected, or pending.",
    ),
    name: str = Query(None),
    db: Session = Depends(get_db),
):
    return await provider.get_request_details(
        db=db,
        skip=skip,
        limit=limit,
        provider_id=provider_id,
        client_id=client_id,
        status=status,
        name=name,
    )


@router.put("/request-status/{request_id}")
async def update_status(
    request_id: UUID,
    status_update: schemas.RequestUpdate,
    db: Session = Depends(get_db),
):
    return await provider.update_request_status(request_id, status_update, db)


@router.get("/service-provider-dashboard")
def get_service_provider_dashboard(
    service_provider_uuid: UUID, db: Session = Depends(get_db)
):
    return provider.get_service_provider_dashboard(service_provider_uuid, db)
