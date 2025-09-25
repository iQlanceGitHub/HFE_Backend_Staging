from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List,Optional
from uuid import UUID

# from src.models.models import User
from fastapi import File, UploadFile
from pydantic import UUID4, BaseModel, EmailStr, Field

from src.common.dto import Dto


@dataclass
class ExampleCompany:
    company_id: int
    company_name: str
    gpt_name: str


@dataclass
class OpportunityData(Dto):
    index: int
    opportunity: str
    examples_of_companies_in_the_space: List[ExampleCompany]

class OrganizationTypeUpdate(BaseModel):
    name: str | None = None
    updated_by: UUID4 | None = Field(
        default=None, description="User who updated the organization type"
    )

class SiteSettingsCreate(BaseModel):
    site_name : str | None = None
    website_link: str | None = None
    contact_number: str | None = None
    contact_email: str | None = None
    address: str | None = None

# class User(BaseModel):
#     email: str
#     password: str
#     role: str


# class UserResponse(BaseModel):
#     user_id: int
    
class OrganizationTypeCreate(BaseModel):
    name: List[str]
    created_by: UUID4

class FAQCreate(BaseModel):
    details: List[Dict[str, Any]] | None = None
    created_by: UUID4
    role_type: str

class FAQUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    updated_by: UUID4 | None = Field(
        default=None, description="User who updated the FAQ details"
    )
    # role_type: str | None = None 

class Login(BaseModel):
    useremail: str
    password: str

class UpdateSubcategory(BaseModel):
    sub_category_id: int
    status: bool 
    uuid: str | None = None

class UpdateapproveCategory(BaseModel):
    uuid: str | None = None


class TitaniumResponse(BaseModel):
    name: str
    subscriptionName: str
    clients_count: int
    price: int
    duration: str
    chat_restrictions: bool
    communications: str
    risk_reward_clients: bool
    risk_reward_prospective_clients: bool
    risk_reward_provider: bool
    providerId: UUID4
    successurl: str
    cancelurl: str


class Token(BaseModel):
    uuid: UUID4
    access_token: str
    token_type: str
    expiry_time: str
    role_type: str
    name: str
    profile_img: str | None
    subscription: dict | None = None
    first_name: str | None = None
    last_name: str | None = None
    ssn: str | None = None
    gender: str | None = None
    address_1: str | None = None
    primary_needs: int | None = None
    city: str | None = None
    created_by_role: str | None = None
    created_by: UUID4 | None = None
    customer_id: str | None = None


class TokenData(BaseModel):
    useremail: str | None = None


class QuestionEnum(str, Enum):
    OPTION_A = "yes"
    OPTION_B = "no"


class ServiceProviderBase(BaseModel):
    admin_uuid: UUID4
    name: str
    organization_type: str
    contact_title: str | None
    contact_name: str
    phone: str
    email: EmailStr
    website_link: str
    description: str

class AssginClients(BaseModel):
    uuid: UUID4
    clients:List[str]

class AssginProviders(BaseModel):
    uuid: UUID4
    providers: List[str]


class ServiceProviderCreate(ServiceProviderBase):
    pass


class ServiceProviderResponse(BaseModel):
    uuid: UUID4
    created_by: UUID4

    class Config:
        from_attributes = True


# class ServiceProviderResponseAll(BaseModel):
#     uuid: UUID4
#     name: str | None
#     estimated_clients: int | None = None
#     tax_id: str | None
#     role_type: str
#     contact_title: str
#     contact_name: str
#     contact_email: EmailStr | None
#     founder_name: str | None
#     address_1: str | None
#     city: str | None
#     country: str |None
#     category_id: int | None = None
#     is_activated: bool
#     status: str
#     created_by_role_type:str
#     class Config:
#         from_attributes = True


class ServiceProviderResponseget(BaseModel):
    uuid: UUID4
    name: str | None
    phone: str | None
    estimated_clients: int | None = None
    tax_id: str | None
    role_type: str
    contact_title: str | None
    contact_name: str
    email: EmailStr | None
    # contact_email: EmailStr | None
    founder_name: str | None
    address_1: str | None
    city: str | None
    country: str | None
    category_id: str | None = None
    sub_category_id: str | None = None
    is_activated: bool
    status: str
    created_at: datetime
    service_provider_type: str
    website_link: str
    comments: str

    class Config:
        from_attributes = True


# class ListofServiceProviderResponse(BaseModel):
#     total_service_provider: int
#     service_provider: List[ServiceProviderResponseget]


class StatusUpdate(BaseModel):
    status: str
    refuted_message: str | None = None


class ClientBase(BaseModel):
    admin_uuid: UUID4
    useremail: EmailStr
    first_name: str
    last_name: str
    dob: str | None = None  # Keep as string for front-end compatibility (MM-DD-YYYY)
    ssn: str | None = None
    gender: str = "Male"
    address_1: str
    address_2: str | None = None
    city: str
    county: str
    state: str
    zip_code: str
    region: str | None = None
    lat: str | None = None
    long: str | None = None
    phone: str | None = None
    website_link: str | None = None
    # profile_img: Optional[UploadFile] = File(None)
    # header_img: Optional[UploadFile] = File(None)

    @classmethod
    def validate_dob(cls, value):
        try:
            return datetime.strptime(value, "%m-%d-%Y").date()
        except ValueError:
            raise ValueError("Date of birth must be in MM-DD-YYYY format.")

    class Config:
        from_attributes = True


class ClientCreate(ClientBase):
    pass


# class ClientUpdate(ClientBase):
#     pass


class ClientResponse(BaseModel):
    user_id: int
    client_id: int
    # created_at: datetime
    # updated_at: datetime

    class Config:
        from_attributes = True

class CountyRegion(BaseModel):
    county: Optional[str] = None
    region: Optional[str] = None

class ClientResponseget(BaseModel):
    uuid: UUID4
    first_name: str | None
    last_name: str | None
    gender: str
    phone: str | None
    email: EmailStr | None
    county: str | None
    state: str | None
    city: str | None
    zip_code: str | None
    region: str | None
    county_region: CountyRegion | None
    lat: str | None
    long: str | None
    country: str | None
    ssn: str | None
    dob: str | None
    housing_situation: str | None
    website_link: str | None
    address_1: str | None
    address_2: str | None
    Question: str | None
    socialmedia_links: List[str] | None
    comments: str | None
    primary_need_id: int | None
    primary_need: str | None
    secondary_need_ids: List[int] | None
    secondary_need: List[str] | None
    is_activated: bool
    profile_img: str | None
    header_img: str | None
    resume: str | None
    created_by_role_type: str | None
    created_by: UUID | None
    updated_at: datetime
    created_at: datetime
    is_deleted: bool
    deleted_at: datetime | None
    rating: float | None
    approved_by: UUID | None

    class Config:
        from_attributes = True


class ListofClientResponse(BaseModel):
    total_client: int
    client: List[ClientResponseget]


class UpdateClient(BaseModel):
    admin_uuid: UUID4
    first_name: str | None
    last_name: str | None
    dob: str | None
    ssn: str | None
    gender: str | None
    address_1: str | None
    address_2: str | None
    city: str | None
    county: str | None
    state: str | None
    zip_code: str | None
    region: str | None = None
    lat: str | None = None
    long: str | None = None
    website_link: str | None
    housing_situation: str | None = None
    Question: str | None = None
    socialmedia_links: list[str] | None = None
    country: str | None = None
    useremail: EmailStr | None = None
    phone: str | None = None


class UpdateClientResponse(BaseModel):
    client_uuid: UUID4
    updated_at: datetime
    updated_by: UUID4

    class Config:
        from_attributes = True


class SoftDeleteClient(BaseModel):
    deleted_by: str


# class SubAdminBase(BaseModel):
#     admin_id: int
#     module_service_provider: bool | None = False
#     module_client: bool | None = False


class SubAdminCreate(BaseModel):
    uuid: UUID4
    first_name: str
    last_name: str
    useremail: EmailStr
    phone: str
    gender: str = Field(default="Male")
    permission: dict = Field(
        default={
            "client": {
                "add": False,
                "import": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "service_provider": {
                "add": False,
                "import": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "quetionaries": {
                "add": False,
                "edit": False,
                "delete": False,
            },
            "categories": {
                "add": False,
                "edit": False,
                "delete": False,
            },
            "revenue": {
                "download": False,
            },
            "subscription": {
                "add": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "ad/banner": {
                "add": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "broadcasting": {
                "add": False,
                "delete": False,
                "active": False,
            },
        },
        description="Permission settings for the sub-admin",
    )
    password: str
    profile_img: UploadFile | None = File(None)
    header_img: UploadFile | None = File(None)


# class SubAdminUpdate(SubAdminBase):
#     pass


class SubAdminResponse(BaseModel):
    uuid: UUID4
    first_name: str
    last_name: str
    phone: str
    useremail: EmailStr
    profile_img: str | None
    is_activated: bool

    class Config:
        from_attributes = True


# class ListofSubAdminResponse(BaseModel):
#     total_subadmins: int
#     subadmins: List[SubAdminResponse]


class Rating(BaseModel):
    client_uuid: UUID4
    service_provider_uuid: UUID4
    question_answer: Dict[str, int | str]
    rated_by: str

    class Config:
        from_attributes = True


class ResumeUploadBase(BaseModel):
    client_id: int
    file_type: str
    file_path: str
    file_size: int


# class ResumeUploadCreate(ResumeUploadBase):
#     pass


# class ResumeUploadResponse(ResumeUploadBase):
#     file_id: int
#     created_at: datetime
#     updated_at: datetime

#     class Config:
#         from_attributes = True


class PriceDetail(BaseModel):
    amount: int
    discount: int | None = 0
    stripe_price_id: str | None = None


class createSubscription(BaseModel):
    name: str
    description: str
    clients_count: int
    view_other_client: str = Field(
        default=None, examples=["none", "local", "regional", "statewide", "multistate"]
    )
    chat_with_prospective_clients: bool
    chat_restriction: bool
    risk_reward_clients: bool
    risk_reward_prospective_clients: bool
    risk_reward_provider: bool
    price_details: dict[str, PriceDetail]
    created_by: UUID4


class PriceDetailResponse(BaseModel):
    amount: int
    discount: int | None = 0
    stripe_price_id: str | None = (
        None  # Ensure stripe_price_id is included in the response
    )


class SubscriptionResponse(BaseModel):
    subscription_id: int
    name: str
    description: str
    clients_count: int
    view_other_client: str = Field(
        default=None, examples=["none", "local", "regional", "statewide", "multistate"]
    )
    chat_with_prospective_clients: bool
    chat_restriction: bool
    risk_reward_clients: bool
    risk_reward_prospective_clients: bool
    risk_reward_provider: bool
    price_details: dict[str, PriceDetail]

    class Config:
        from_attributes = True


class updateSubscriptionresponse(BaseModel):
    subscription_id: int
    name: str
    description: str
    clients_count: int
    view_other_client: str = Field(
        default=None, examples=["none", "local", "regional", "statewide", "multistate"]
    )
    chat_with_prospective_clients: bool
    chat_restriction: bool
    risk_reward_clients: bool
    risk_reward_prospective_clients: bool
    risk_reward_provider: bool
    price_details: dict[str, PriceDetail]
    created_by: UUID4
    updated_by: UUID4

    class Config:
        from_attributes = True


# class PriceDetailUpdate(BaseModel):
#     amount: int
#     discount: Optional[int] = 0
#     stripe_price_id: Optional[str] = None


class updateSubscription(BaseModel):
    name: str
    description: str
    clients_count: int
    view_other_client: str = Field(
        default=None, examples=["none", "local", "regional", "statewide", "multistate"]
    )
    chat_with_prospective_clients: bool
    chat_restriction: bool
    risk_reward_clients: bool
    risk_reward_prospective_clients: bool
    risk_reward_provider: bool
    price_details: dict[str, PriceDetail]
    updated_by: UUID4


class ListofSubscriptionResponse(BaseModel):
    total_subscriptions: int
    all_subscriptions: List[SubscriptionResponse]


# class createMembership(BaseModel):
#     service_provider_id: int
#     subscription_id: int
#     duration: int
#     expiry: int


# class createMembershipResponse(BaseModel):
#     service_provider_id: int
#     subscription_id: int
# duration: int
# expiry: int


# class updateMembership(BaseModel):
#     subscription_id: int | None = None
#     duration: int | None = None
#     expiry: int | None = None


class CategoryBase(BaseModel):
    uuid: UUID4
    category_name: str
    sub_category_name: List[str] | None = None


class CategoryCreate(CategoryBase):
    pass


class SubCategoryResponse(BaseModel):
    sub_category_id: int
    sub_category_name: str
    # created_at: datetime
    # updated_at: datetime

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    category_id: int
    category_name: str
    sub_category_name: List[SubCategoryResponse]
    # created_at: datetime
    # updated_at: datetime

    class Config:
        from_attributes = True


class ListofCategoryResponse(BaseModel):
    total_categories: int
    categories: List[CategoryResponse]


class UpdateCategory(BaseModel):
    category_name: str | None = None
    sub_category: List[Optional[Dict]] | None = None
    updated_by: UUID4


class SubCategoryBase(BaseModel):
    uuid: UUID4
    category_id: int
    sub_category_name: str


class SubCategoryCreate(SubCategoryBase):
    pass


class UpdateSubCategory(BaseModel):
    sub_category_name: str
    updated_by: UUID4
    category_id: int



class createNotification(BaseModel):
    client_id: int
    service_provider_id: int
    title: str
    message: str


# class showNotification(BaseModel):
#     service_provider_id: int


class ChatBase(BaseModel):
    sender_id: UUID4
    receiver_id: UUID4
    message: str


class ChatCreate(ChatBase):
    pass


# class Chat(ChatBase):
#     chat_id: int
#     created_at: datetime
#     updated_at: datetime

#     class Config:
#         from_attributes = True


class MessageBase(BaseModel):
    chat_id: int
    sender_id: UUID4
    message: str | None


class MessageCreate(MessageBase):
    pass


class AttachmentResponse(BaseModel):
    name: str | None = None
    url: str
    type: str | None = None
    size: int | None = 0


class Message(MessageBase):
    message_id: int
    sent_at: datetime
    is_read: bool
    created_at: datetime
    updated_at: datetime
    attachment: List[AttachmentResponse] | None = []

    # attachment_type: Optional[List[str]] = []
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    message_id: int  # Add message_id
    chat_id: int
    sender_id: UUID4
    message: str | None
    attachment: List[AttachmentResponse | None] | None = []
    profile_img: str | None = None
    receiver_email: str | None = None
    sent_at: datetime  # Add sent_at

    class Config:
        from_attributes = True


class MediaResponse(BaseModel):
    message_id: int
    sender_id: UUID4
    attachment: str | None  # URL for the attachment
    attachment_type: str | None  # MIME type of the attachment
    name: str | None = None
    size: int | None = 0
    sent_at: datetime

    class Config:
        from_attributes = True


class ForgotPassword(BaseModel):
    email: EmailStr


# class OTP(BaseModel):
#     otp: int

# class ResetPassword(BaseModel):
#     new_password: str
#     confirm_password: str


class QuestionType(BaseModel):
    question_type_name: str


class OptionCreate(BaseModel):
    question_id: int
    option_text: str


class QuestionCreate(BaseModel):
    question_text: str
    question_type: int
    is_mandatory: bool | None = False
    parent_id: int | None = None


class QuestionUpdate(BaseModel):
    question_id: int
    question_text: str
    question_type: int
    is_mandatory: bool | None = False
    options: List[OptionCreate] | None


class QuestionResponse(BaseModel):
    question_id: int
    question_text: str
    question_type: QuestionType
    is_mandatory: bool | None = False
    created_at: datetime

    class Config:
        from_attributes = True


class SubQuestionCreate(BaseModel):
    question_id: int
    subquestion_text: str
    subquestion_type: int
    is_mandatory: bool | None = False


class QuestionDelete(BaseModel):
    question_id: int


class Gender(str, Enum):
    male = "male"
    female = "female"


class editSubAdmin(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    gender: str | None = None
    email: EmailStr | None = None,
    phone: str | None = None,
    permission: Dict[str, Any] | None = Field(
        default={
            "client": {
                "add": False,
                "import": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "service_provider": {
                "add": False,
                "import": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "quetionaries": {
                "add": False,
                "edit": False,
                "delete": False,
            },
            "categories": {
                "add": False,
                "edit": False,
                "delete": False,
            },
            "revenue": {
                "download": False,
            },
            "subscription": {
                "add": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "ad/banner": {
                "add": False,
                "edit": False,
                "delete": False,
                "active": False,
            },
            "broadcasting": {
                "add": False,
                "delete": False,
                "active": False,
            },
        },
        description="Permission settings for the sub-admin",
    )
    updated_by: UUID4 | None = Field(
        default=None, description="User who updated the sub-admin details"
    )


class Admin(BaseModel):
    name: str
    useremail: EmailStr
    password: str


class AdminResponse(BaseModel):
    useremail: str

    class Config:
        from_attributes = True

class AdminUpdateServiceProvider(BaseModel):
    admin_uuid: UUID4
    categories: Optional[str] = None
    name: Optional[str] = None
    estimated_clients: Optional[int] = None
    organization_type: Optional[str] = None
    tax_id: Optional[str] = None
    contact_title: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    founder_first_name: Optional[str] = None
    founder_last_name: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    long: Optional[float] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    socialmedia_links: Optional[List[str]] = None
    website_link: Optional[str] = None
    question: Optional[str] = None
    category_id: Optional[int] = None
    sub_category_id: Optional[int] = None
    description: Optional[str] = None
    rating: Optional[float] = None
    client_count: Optional[int] = None
    subscription: Optional[str] = None
    staff_first_name: Optional[str] = None
    staff_last_name: Optional[str] = None


class UpdateServiceProviderResponse(BaseModel):
    service_provider_uuid: UUID4
    updated_at: datetime
    updated_by: UUID4

    class Config:
        from_attributes = True


class SoftDeleteServiceProvider(BaseModel):
    deleted_by: str


class SoftDeleteRequest(BaseModel):
    deleted_by: str


class AdBanner(BaseModel):
    created_by_uuid: UUID4
    alternative_text: str
    category_id: int
    link: str
    # image_url: str


class UpdateAdBanner(BaseModel):
    updated_by_uuid: UUID4 | None
    alternative_text: str | None
    category_id: int | None
    link: str | None
    image_url: UploadFile | None


class BroadcastMessageBase(BaseModel):
    created_by: UUID4
    title: str
    message: str
    recipients: List[UUID4]  # Assuming recipients are UUIDs


class BroadcastMessageCreate(BroadcastMessageBase):
    pass


# class BroadcastMessage(BroadcastMessageBase):
#     broadcast_id: int
#     created_at: str
#     created_by: Optional[UUID4]

#     class Config:
#         from_attributes = True


class CreateServiceProvider(BaseModel):
    name: str | None
    # service_provider_type: Optional[str] | None
    estimated_clients: int
    tax_id: str  # constr(max_length=9, min_length=9)
    organization_type: str
    contact_title: str | None
    contact_name: str
    contact_email: EmailStr
    founder_first_name: str | None
    founder_last_name: str | None
    address_1: str
    address_2: str | None
    county: str | None
    city: str
    country: str | None
    state: str
    zip_code: str | None  # constr(max_length=10)
    region: str | None = None
    lat: str | None = None
    long: str | None = None
    phone: str | None  # constr(max_length=15)
    email: EmailStr | None
    gender: str | None
    socialmedia_links: List[str] | None = None
    website_link: str | None
    question: QuestionEnum
    description: str
    password: str
    categories: str | None = None 
    keywords: List[str] | None = None


class AddSubscription(BaseModel):
    # service_provider_uuid: UUID4
    subscription_id: int | None
    payment_method: str | None
    payment_intent: str | None
    payment_intent_client_secret: str | None
    redirect_status: str | None
    duration: str


class UpdateServiceProvider(BaseModel):
    updated_by: UUID4
    name: str | None = None
    # service_provider_type: Optional[str] = None
    organization_type: str | None = None
    estimated_clients: str | None = None
    tax_id: str | None = None
    contact_title: str | None = None
    contact_name: str | None = None
    contact_email: EmailStr | None = None
    founder_first_name: str | None = None
    founder_last_name: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    county: str | None = None
    city: str | None = None
    country: str | None = None
    state: str | None = None
    zip_code: str | None = None
    region: str | None = None
    lat: str | None = None
    long: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    socialmedia_links: str | None = None
    website_link: str | None = None
    comments: str | None = None
    question: str | None = None
    profile_img: str | None = None
    header_img: str | None = None
    description: str | None = None
    brochure: str | None = None
    socialmedia_links: List[str] | None = None
    categories: str | None = None 
    keywords: List[str] | None = None
    password: str | None = None


class ProviderStaff(BaseModel):
    uuid: UUID4
    first_name: str
    last_name: str
    useremail: EmailStr
    phone: str
    gender: str = Field(default="Male")
    permission: dict = Field(
        default={
            "subscription": {"upgrade_downgrade": False},
            "client": {"add": False, "import": False, "edit": False, "delete": False},
            "service_provider": {
                "add": False,
                "import": False,
                "edit": False,
                "delete": False,
            },
            "chat": {"chat_client": False, "chat_provider": False},
        },
        description="Permission settings for the sub-admin",
    )
    password: str
    profile_img: UploadFile | None = File(None)
    header_img: UploadFile | None = File(None)


class editProviderStaff(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    gender: str | None = None
    useremail: EmailStr | None = None
    phone: str | None = None
    permission: Dict[str, Any] | None = Field(
        default={
            "subscription": {"upgrade_downgrade": False},
            "client": {"add": False, "import": False, "edit": False, "delete": False},
            "service_provider": {
                "add": False,
                "import": False,
                "edit": False,
                "delete": False,
            },
            "chat": {"chat_client": False, "chat_provider": False},
        },
        description="Permission settings for the staff",
    )
    updated_by: UUID4 | None = Field(
        default=None, description="User who updated the sub-admin details"
    )


class QuestionEnumClient(str, Enum):
    OPTION_A = "probation"
    OPTION_B = "parole"
    OPTION_C = "discharged"
    OPTION_D = "none of above"


class IntList(list):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, str):
            # If a comma exists, split into multiple items,
            # otherwise treat it as a single integer.
            if "," in v:
                return cls([int(i.strip()) for i in v.split(",") if i.strip()])
            return cls([int(v.strip())])
        elif isinstance(v, list):
            # Convert each element to int
            return cls([int(i) for i in v])
        raise ValueError("Invalid input for category list.")


class CreateClient(BaseModel):
    useremail: EmailStr
    first_name: str
    last_name: str
    dob: str | None = None
    ssn: str | None = None
    gender: str
    housing_situation: str | None = None
    Question: QuestionEnumClient | None = None
    address_1: str
    address_2: str | None = None
    city: str
    county: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    region: str | None = None
    lat: str | None = None
    long: str | None = None
    phone: str | None = None
    website_link: str | None = None
    socialmedia_links: List[str] | None = None
    skills: List[str] | None = None
    question: str | None = None
    primary_need: int
    secondary_need: List[int] | None = None
    # category_id: List[int]
    # other_category_id: Optional[int] = None
    password: str

    class Config:
        use_enum_values = True


class PaymentRequest(BaseModel):
    stripeToken: str
    amount: int


class RequestBase(BaseModel):
    client_id: UUID4
    provider_id: UUID4
    # request_details: str


class RequestCreate(RequestBase):
    pass


class RequestResponse(RequestBase):
    id: UUID4
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RequestUpdate(BaseModel):
    status: str


class UpdateClientSetting(BaseModel):
    client_uuid: UUID4
    first_name: str | None = None
    last_name: str | None = None
    dob: str | None = None
    ssn: str | None = None
    gender: str = "Male"
    housing_situation: str | None = None
    Question: QuestionEnumClient | None = None
    question: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    county: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip_code: str | None = None
    phone: str | None = None
    region: str | None = None
    lat: str | None = None
    long: str | None = None
    website_link: str | None = None
    useremail : EmailStr | None = None
    # socialmedia_links: Optional[str] = None
    socialmedia_links: List[str] | None = None
    skills: List[str] | None = None
    primary_need: int | None = None
    secondary_need: List[int] | None = None


class FavoriteUser(BaseModel):
    favorite_by: UUID4
    favorite_to: UUID4


class BlockedUser(BaseModel):
    blocked_by: UUID4
    blocked_to: UUID4


class MessageCreate(BaseModel):
    chat_id: int
    sender_id: UUID
    message: str | None = None  # Message can be optional (in case of attachments)

    class Config:
        from_attributes = True


# ------------------ User Schema ------------------ #
class UserCreate(BaseModel):
    useremail: EmailStr
    password: str
    role_type: str
    details: dict  # This will store user-specific details (client, provider, etc.)

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    uuid: UUID
    useremail: EmailStr
    role_type: str

    class Config:
        from_attributes = True


# ------------------ Notification Schema ------------------ #
class NotificationCreate(BaseModel):
    user_id: UUID
    sender_id: UUID | None = None
    message: str

    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    notification_id: int
    user_id: UUID
    # sender_id: Optional[UUID]
    title: str
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DeleteChatUser(BaseModel):
    user_id: UUID4


class ChangeAssessment(BaseModel):
    primary_need: int | None = None
    secondary_need: List[int] | None = None


class RatingQuestion(BaseModel):
    user_id: UUID4
    question_text: str
    target_user: str
    chronological_order: int | None = None
    is_mandatory: bool | None = None


class UpdateRatingQuestion(BaseModel):
    question_id: int
    updated_by: UUID4
    question_text: str | None = None
    target_user: str | None = None
    chronological_order: int | None = None
    is_mandatory: bool | None = None


class SignUpDocumentType(str, Enum):
    CLIENT_TERMS = ("client_terms_and_conditions",)
    CLIENT_PRIVACY = ("client_privacy_policy",)
    PROVIDER_TERMS = ("provider_terms_and_conditions",)
    PROVIDER_PRIVACY = "provider_privacy_policy"


class SignUpDocumentBase(BaseModel):
    title: str
    content: str
    document_type: SignUpDocumentType


class SignUpDocumentCreate(SignUpDocumentBase):
    pass


class SignUpDocumentResponse(SignUpDocumentBase):
    id: int
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True

class ContactUs(BaseModel):
    name: str = None
    roleType: str = None
    address: str = None
    phone : int = None
    email : str = None
    website : str = None
    type : str
    message:str = None
