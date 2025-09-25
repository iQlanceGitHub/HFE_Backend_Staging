import asyncio
import json
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import UUID4, EmailStr
from sqlalchemy.orm import Session

from src.api import schemas
from src.api.schemas import (
    CreateClient,
    UpdateClientSetting,
)
from src.common import client
from src.configs import database

get_db = database.get_db


router = APIRouter(prefix="/client", tags=["Clients"])

@router.post("/client")
def create_client_self(
    request: Request,
    useremail: EmailStr = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    dob: str | None = Form(None),  # you might need to convert this to a date if required
    ssn: str | None = Form(None),
    gender: str = Form("Male"),
    housing_situation: str | None = Form(None),
    Question: str | None = Form(None),
    address_1: str = Form(...),
    address_2: str | None = Form(None),
    city: str = Form(...),
    county: str = Form(...),
    state: str | None = Form(None),
    country: str | None = Form(None),
    zip_code: str | None = Form(None),
    region: str = Form(...),
    lat: str = Form(...),
    long: str = Form(...),
    phone: str | None = Form(None),
    website_link: str | None = Form(None),
    socialmedia_links: str | None = Form(None),
    skills: str | None = Form(None),
    question: str = Form(None),
    primary_need: int = Form(...),
    secondary_need: str | None = Form(None),  # Accept as a comma-separated string
    password: str = Form(...),
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    avatar_selection: str | None = Form(None),
    resume: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    # Convert the comma-separated string into a list of integers
    if secondary_need:
        try:
            secondary_need_list = [
                int(item.strip()) for item in secondary_need.split(",")
            ]
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "secondary_need must be a comma separated list of integers."
                },
            )
    else:
        secondary_need_list = []

    # Process social media links and skills as lists
    socialmedia_links_list = (
        [link.strip() for link in socialmedia_links.split(",")]
        if socialmedia_links
        else []
    )
    skills_list = [skill.strip() for skill in skills.split(",")] if skills else []

    # Create Pydantic model with the converted list
    client_data = CreateClient(
        useremail=useremail,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        ssn=ssn,
        gender=gender,
        housing_situation=housing_situation,
        Question=Question,
        address_1=address_1,
        address_2=address_2,
        city=city,
        county=county,
        state=state,
        country=country,
        zip_code=zip_code,
        region=region,
        lat=lat,
        long=long,
        phone=phone,
        question=question,
        primary_need=primary_need,
        secondary_need=secondary_need_list,  # Passing the list of integers
        website_link=website_link,
        socialmedia_links=socialmedia_links_list,
        skills=skills_list,
        password=password,
    )

    return asyncio.run(
        client.create_client_self(
            request, client_data, profile_img, header_img, avatar_selection, resume, db
        )
    )


@router.patch("/client")
def update_client_self(
    request: Request,
    client_uuid: UUID4,
    first_name: str = Form(None),
    last_name: str = Form(None),
    dob: str | None = Form(None),
    ssn: str | None = Form(None),
    gender: str = Form(...),
    housing_situation: str | None = Form(None),
    Question: str | None = Form(None),
    question: str | None = Form(None),
    address_1: str = Form(None),
    address_2: str | None = Form(None),
    city: str = Form(None),
    county: str | None = Form(None),
    state: str | None = Form(None),
    country: str | None = Form(None),
    zip_code: str | None = Form(None),
    region: str | None = Form(None),
    lat: str | None = Form(None),
    long: str | None = Form(None),
    phone: str | None = Form(None),
    website_link: str = Form(None),
    socialmedia_links: str | None = Form(None),
    skills: str | None = Form(None),
    primary_need: int | None = Form(None),
    secondary_need: str | None = Form(None),  # Accept as a comma-separated string
    profile_img: UploadFile = File(None),
    header_img: UploadFile = File(None),
    resume: UploadFile | str | None = File(None),
    useremail: EmailStr | None = Form(None),
    db: Session = Depends(get_db),
    
):
    # Convert resume string 'null' or empty string to None
    if isinstance(resume, str) and (resume == "null" or resume.strip() == ""):
        resume = None

    # Process social media links
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

    # Process skills list
    skills_list = [skill.strip() for skill in skills.split(",")] if skills else []

    # Convert the comma-separated string for secondary_need into a list of integers
    if secondary_need:
        try:
            secondary_need_list = [
                int(item.strip()) for item in secondary_need.split(",")
            ]
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "secondary_need must be a comma-separated list of integers."
                },
            )
    else:
        secondary_need_list = []

    client_data = UpdateClientSetting(
        client_uuid=client_uuid,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        ssn=ssn,
        gender=gender,
        housing_situation=housing_situation,
        Question=Question,
        question=question,
        address_1=address_1,
        address_2=address_2,
        city=city,
        county=county,
        state=state,
        country=country,
        zip_code=zip_code,
        region=region,
        lat=lat,
        long=long,
        phone=phone,
        website_link=website_link,
        socialmedia_links=socialmedia_links_list,
        skills=skills_list,
        primary_need=primary_need,
        useremail=useremail,
        secondary_need=secondary_need_list,  # Pass the converted list of integers
    )
    return asyncio.run(
        client.update_client_self(
            request, client_uuid, useremail,client_data, profile_img, header_img, resume, db
        )
    )


@router.post("/service-provider-rating")
def create_provider_rating(rating: schemas.Rating, db: Session = Depends(get_db)):
    return client.service_provider_rating(rating, db)


@router.post("/send-request", response_model=schemas.RequestResponse)
async def send_request(
    request_data: schemas.RequestCreate, db: Session = Depends(get_db)
):
    return await client.send_request(request_data, db)


@router.patch("/change-assessment")
def change_assessment(
    client_uuid: UUID, need: schemas.ChangeAssessment, db: Session = Depends(get_db)
):
    return client.change_assessment(client_uuid, need, db)


@router.get("/client-dashboard")
def get_client_dashboard(client_uuid: UUID, db: Session = Depends(get_db)):
    return client.get_client_dashboard(client_uuid, db)
