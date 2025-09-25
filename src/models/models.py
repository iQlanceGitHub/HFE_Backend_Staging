import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    VARCHAR,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import relationship
from src.configs.database import Base


class User(Base):
    __tablename__ = "users"

    uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    useremail = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    role_type = Column(String(50))
    category_id = Column(JSONB,nullable=True)
    is_claimed = Column(Boolean, default=False)
    is_imported = Column(Boolean, default=False)
    is_titanium_requested = Column(Boolean, default=False)
    service_provider_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    details = Column(
        JSONB,
        default={
            "admin": {
                "name": None,
            },
            "service_provider": {
                "name": None,
                "estimated_clients": None,
                "organization_type": None,
                "tax_id": None,
                "contact_title": None,
                "contact_name": None,
                "contact_email": None,
                "founder_first_name": None,
                "founder_last_name": None,
                "address_1": None,
                "address_2": None,
                "county": None,
                "city": None,
                "country": None,
                "state": None,
                "zip_code": None,
                "region": None,
                "lat": None,
                "long": None,
                "phone": None,
                "email": None,
                "gender": None,
                "socialmedia_links": None,
                "website_link": None,
                "question": None,
                "category_id": None,
                "sub_category_id": None,
                "description": None,
                "brochure": None,
                "comments": None,
                "rating": None,
                "client_count": None,
                "subscription": None,
                "staff_first_name": None,
                "staff_last_name": None,
                "keywords":None
            },
            "sub_admin": {
                "first_name": None,
                "last_name": None,
                "gender": "Male",
                "phone": None,
                "email": None,
            },
            "sub_service_provider": {
                "first_name": None,
                "last_name": None,
                "title": None,
                "phone": None,
                "email": None,
            },
            "client": {
                "first_name": None,
                "last_name": None,
                "dob": None,
                "ssn": None,
                "gender": None,
                "housing_situation": None,
                "address_1": None,
                "address_2": None,
                "city": None,
                "county": None,
                "state": None,
                "zip_code": None,
                "region": None,
                "lat": None,
                "long": None,
                "phone": None,
                "Question": None,
                "socialmedia_links": None,
                "website_link": None,
                "comments": None,
                "profile_img": None,
                "header_img": None,
                "ratinng": None,
                "question": None,
                "resume": None,
                "primary_need": None,
                "secondary_need": None,
                # "category_id":None,
                "skills": None,
            },
        },
    )
    permission = Column(
        JSONB,
        default={
            "admin": {
                "can_create_subadmin": True,
                "can_edit_subadmin": True,
                "can_delete_subadmin": True,
            },
            "sub_admin": {
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
        },
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    service_provider_type = Column(String, nullable=False, server_default="individual")
    status = Column(String, nullable=False, server_default="pending")
    is_activated = Column(Boolean, default=False)
    profile_img = Column(String(255), nullable=True)
    header_img = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=datetime.now)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    deleted_at = Column(TIMESTAMP, default=func.now())
    stripe_customer_id = Column(String(255), nullable=True)
    activated_at = Column(TIMESTAMP, nullable=True)

class ExportData(Base):
    __tablename__ = "export_data"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    role_type = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    total_counts = Column(Integer, nullable=False)
    success_counts = Column(Integer, nullable=False)
    fail_counts = Column(Integer, nullable=False)
    upload_date = Column(TIMESTAMP, default=func.now())
    file_path = Column(JSONB, nullable=False, default={})
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=False)
    
class ResumeUpload(Base):
    __tablename__ = "resume_uploads"

    file_id = Column(Integer, primary_key=True, index=True)
    # client_id = Column(Integer, ForeignKey("clients.client_id"), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # client = relationship("Client", back_populates="resumes")

class Faq(Base):
    __tablename__ = "faqs"

    faq_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question = Column(String(1500), nullable=False)
    answer = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp())
    role_type = Column(String(50), nullable=True)

class OrganizationType(Base):
    __tablename__ = "organization_types"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp())

class SiteSettings(Base):
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    site_name = Column(String(100), nullable=False)
    website_link = Column(String(255), nullable=False)
    contact_number = Column(String(50), nullable=False)
    contact_email = Column(String(100), nullable=False)
    address = Column(String(255), nullable=True)
    
class Subscription(Base):
    __tablename__ = "subscriptions"

    subscription_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    description = Column(String(255), nullable=False)
    clients_count = Column(Integer, nullable=False)
    view_other_client = Column(String(150), nullable=False)
    chat_with_prospective_clients = Column(Boolean, default=False)
    chat_restriction = Column(Boolean, default=False)
    risk_reward_clients = Column(Boolean, default=False)
    risk_reward_prospective_clients = Column(Boolean, default=False)
    risk_reward_provider = Column(Boolean, default=False)
    price_details = Column(
        JSONB,
        default={
            "monthly": {"amount": 0, "stripe_price_id": "", "discount": 0},
            "quarterly": {
                "amount": 0,
                "stripe_price_id": "",
                "discount": 0,
            },
            "yearly": {
                "amount": 0,
                "stripe_price_id": "",
                "discount": 0,
            },
        },
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(
        UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=False, index=True
    )
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.subscription_id"), nullable=False
    )
    trial_start_date = Column(DateTime, nullable=True)
    trial_end_date = Column(DateTime, nullable=True)
    billing_date = Column(DateTime, nullable=True)
    start_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())
    duration = Column(String(255))
    payment_price = Column(Integer)
    payment_status = Column(String(50), default="pending")
    status = Column(String)
    stripe_subscription_id = Column(String(255), nullable=True)


class Titanium(Base):
    __tablename__ = "titanium"

    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(
        UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=False, index=True
    )
    clients_count = Column(Integer, nullable=False)
    chat_restriction = Column(Boolean, default=False)
    view_other_client = Column(String(150), nullable=False)
    risk_reward_clients = Column(Boolean, default=False)
    risk_reward_prospective_clients = Column(Boolean, default=False)
    risk_reward_provider = Column(Boolean, default=False)
    start_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())
    duration = Column(String(255))
    status = Column(String)
    payment_price = Column(Integer)
    payment_status = Column(String(50), default="pending")


class Category(Base):
    __tablename__ = "categories"

    category_id = Column(Integer, primary_key=True, index=True)
    category_name = Column(String(25), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    is_approved = Column(Boolean, default=False)
    other_category_id = Column(Integer, nullable=True)
    subcategories = relationship(
        "SubCategory", back_populates="category", cascade="all, delete-orphan"
    )


class SubCategory(Base):
    __tablename__ = "subcategories"

    sub_category_id = Column(Integer, primary_key=True, index=True)
    category_id = Column(
        Integer,
        ForeignKey("categories.category_id", ondelete="CASCADE"),
        nullable=False,
    )
    sub_category_name = Column(String(255), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    is_approved = Column(Boolean, default=False)

    category = relationship("Category", back_populates="subcategories")


class Notification(Base):
    __tablename__ = "notification"

    notification_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.uuid"),
        nullable=True,
    )  # Target user
    # client_id = Column(Integer, ForeignKey("clients.client_id"), nullable=False)
    # service_provider_id = Column(Integer, ForeignKey("service_providers.service_provider_id"),nullable=False)
    title = Column(VARCHAR(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    type = Column(VARCHAR(100), nullable=True)


class Chat(Base):
    __tablename__ = "chats"

    chat_id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(UUID, ForeignKey("users.uuid"), nullable=False)
    receiver_id = Column(UUID, ForeignKey("users.uuid"), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(TIMESTAMP, default=func.now())
    deleted_by = Column(ARRAY(UUID), default=[])
    end_chat = Column(Boolean, default=False)


class Message(Base):
    __tablename__ = "messages"

    message_id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.chat_id"), nullable=False)
    sender_id = Column(UUID, nullable=False)
    message = Column(Text, nullable=True)
    attachment = Column(JSONB, nullable=True, default=list)
    # attachment_type = Column(JSONB, nullable=True, default=list)
    sent_at = Column(TIMESTAMP, default=func.now())
    is_read = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(TIMESTAMP, default=func.now())
    # deleted_by = Column(JSONB, nullable=True)

    # chat = relationship("Chat", back_populates="messages")
    # attachments = relationship("ChatAttachment", back_populates="message")


class AdBanner(Base):
    __tablename__ = "ad-banner"

    adbanner_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alternative_text = Column(Text, nullable=False)
    category_id = Column(Integer, nullable=False)
    link = Column(Text, nullable=False)
    image_url = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    # is_deleted = Column(Boolean, default=False)
    # deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    # deleted_at = Column(TIMESTAMP, nullable=True)
    is_activated = Column(Boolean, default=True)


class BroadcastMessage(Base):
    __tablename__ = "broadcast_messages"

    broadcast_id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    recipients = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP, default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)


class Question_Type(Base):
    __tablename__ = "question_type"

    question_type_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question_type_name = Column(String(50), nullable=False)


# class Questionnaires(Base):
#     __tablename__ = "questionnaires"

#     id = Column(Integer, primary_key=True, index=True)
#     question_type = Column(
#         Integer, ForeignKey("question_type.question_type_id"), nullable=False
#     )
#     question_text = Column(Text, nullable=False)
#     is_mandatory = Column(Boolean, default=False)
#     parent_id = Column(Integer, ForeignKey("questionnaires.id"), nullable=True)

#     sub_questions = relationship("Questionnaires", backref="parent", remote_side=[id])


class Request(Base):
    __tablename__ = "requests"

    id = Column(UUID, primary_key=True, index=True)
    client_id = Column(UUID, ForeignKey("users.uuid"), nullable=False)
    provider_id = Column(UUID, ForeignKey("users.uuid"), nullable=False)
    # request_details = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default="pending")
    # created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    # updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=datetime.now)


class FavouriteBlocked(Base):
    __tablename__ = "favouriteblocked"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    favourited_by = Column(UUID, ForeignKey("users.uuid"), nullable=True)
    favourited_to = Column(UUID, ForeignKey("users.uuid"), nullable=True)
    blocked_by = Column(UUID, ForeignKey("users.uuid"), nullable=True)
    blocked_to = Column(UUID, ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, default=func.now())
    # updated_at = Column(TIMESTAMP, default=func.now(), onupdate=datetime.now)


class Ratings(Base):
    __tablename__ = "ratings"

    rating_id = Column(
        Integer,
        Sequence("ratings_rating_id_seq", start=1, increment=1),
        primary_key=True,
        index=True,
    )
    client_uuid = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=False)
    service_provider_uuid = Column(
        UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=False
    )
    question_answer = Column(JSONB, nullable=False)
    rated_by = Column(String(50), nullable=False, server_default="undefined")
    average_rating = Column(Float, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class RatingQuestion(Base):
    __tablename__ = "rating_question"

    question_id = Column(Integer, primary_key=True, index=True)
    question_text = Column(String, nullable=False)
    target_user = Column(String, nullable=False)
    chronological_order = Column(Integer)
    is_mandatory = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    deleted_at = Column(TIMESTAMP, default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.uuid"), nullable=True)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=datetime.now)


class Questionnaires(Base):
    __tablename__ = "questionnaires"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ContactUs(Base):
    __tablename__ = "contact_us"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class SignUpDocuments(Base):
    __tablename__ = "signup_documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    document_type = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
