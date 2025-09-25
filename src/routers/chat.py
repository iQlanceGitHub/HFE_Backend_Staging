import asyncio
import base64
import json
import os
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import UUID4
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.api import schemas
from src.common.email_service import send_email
from src.common.tasks import get_notifications as get_chat_notifications
from src.common.tasks import (
    remove_notifications_for_sender,
    remove_notifications_for_user,
    remove_notifications_on_read,
    store_notification,
)
from src.configs import database
from src.configs.config import logger
from src.models import models

get_db = database.get_db
router = APIRouter(tags=["Chats"])

# Dictionary to keep track of connected WebSocket clients
clients: Dict[str, WebSocket] = {}

BASE_DIR_ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR_ = os.path.join(BASE_DIR_, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR_)

# Folder for attachments
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ATTACHMENT = os.path.join(BASE_DIR, "attachments")
os.makedirs(ATTACHMENT, exist_ok=True)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    username = websocket.query_params.get("username")

    if not username:
        logger.log_error("WebSocket connection rejected: no username provided")
        await websocket.close(code=1008)
        return

    logger.log_info(f"User '{username}' connected via WebSocket")
    clients[username] = websocket
    logger.log_info(f"Active clients: {list(clients.keys())}")

    try:
        while True:
            try:
                message = await websocket.receive()
            except (WebSocketDisconnect, RuntimeError) as e:
                logger.log_info(f"User '{username}' disconnected: {e}")
                break

            # Process message
            data = message.get("text") or message.get("bytes", b"").decode("utf-8")
            if not data:
                continue

            logger.log_info(f"Received from '{username}': {data}")

            try:
                message_data = json.loads(data)
            except json.JSONDecodeError as e:
                logger.log_error(f"Invalid JSON from '{username}': {e}")
                await websocket.send_text("Invalid JSON format")
                continue

            # Handle END_CHAT event
            if message_data.get("type") == "END_CHAT":
                await handle_end_chat(username, message_data, websocket)
                continue

            # Process normal message
            await handle_message(username, message_data, websocket)

    except WebSocketDisconnect:
        logger.log_info(f"User '{username}' disconnected")
    finally:
        clients.pop(username, None)


async def handle_end_chat(username: str, message_data: dict, websocket: WebSocket):
    chat_id = message_data.get("chat_id")
    if not chat_id:
        logger.log_warning("No chat_id provided for ending chat")
        await websocket.send_text("No chat_id provided")
        return

    db: Session = next(get_db())
    try:
        chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
        if not chat:
            logger.log_warning(f"Chat {chat_id} not found")
            await websocket.send_text(f"Chat {chat_id} not found")
            return

        # Update chat status
        chat.end_chat = True
        chat.updated_at = datetime.now()
        db.commit()
        logger.log_info(f"Chat {chat_id} ended by '{username}'")

        # Notify participants
        update_message = json.dumps({"event": "chat_ended", "chat_id": chat_id})
        await notify_chat_participants(chat, update_message)
        await websocket.send_text(f"Chat {chat_id} ended successfully")

    except Exception as e:
        logger.log_error(f"Error ending chat {chat_id}: {e}")
        await websocket.send_text(f"Error ending chat: {e}")
    finally:
        db.close()


async def handle_message(username: str, message_data: dict, websocket: WebSocket):
    recipient = message_data.get("recipient")
    message_text = message_data.get("message")
    files_data = message_data.get("files", [])

    if not recipient or message_text is None:
        logger.log_warning(f"Invalid message from '{username}'")
        await websocket.send_text("Invalid message data")
        return
    db: Session = next(get_db())
    # Check if reciept and user are client and provider
    is_prosective_chat, has_prospective_chat_restriction, provider_user = (
        check_for_prospective_chat(username, recipient, db)
    )

    # Process attachments
    attachments = await process_attachments(files_data, username)

    # Save message to database
    chat_id = message_data.get("chat_id", "")

    try:
        if not chat_id:
            chat = await get_or_create_chat(db, username, recipient, message_text)

            if not chat:
                logger.log_warning("No Chat found.")
                await websocket.send_text("No Chat found.")
            else:
                chat_id = chat.chat_id

        if message_text or attachments:
            await save_message(db, chat_id, username, message_text, attachments)
            if (
                is_prosective_chat
                and not has_prospective_chat_restriction
                and recipient == str(provider_user)
            ):
                notification_message_text = "Please Upgrade your Plan."
            elif (
                is_prosective_chat
                and has_prospective_chat_restriction
                and recipient == str(provider_user)
            ):
                notification_message_text = message_text
            else:
                notification_message_text = message_text
            store_notification(recipient, notification_message_text, username)

        if message_data.get("reciever_active_for", ""):
            messages = db.query(models.Message).filter(
                models.Message.chat_id == chat_id,
                models.Message.sender_id == message_data["reciever_active_for"],
            )
            for message in messages:
                message.is_read = True
            remove_notifications_for_sender(
                username, message_data["reciever_active_for"]
            )

        # Send message to recipient
        payload = {
            "sender": username,
            "receiver": recipient,
            "message": message_text,
            "attachments": attachments,
            "type": "MESSAGE" if message_data.get("type", "") == "MESSAGE" else "",
        }
        await deliver_message(recipient, payload, websocket)

    except Exception as e:
        logger.log_error(f"Error processing message from '{username}': {e}")
        await websocket.send_text(f"Error: {e}")
    finally:
        db.close()


async def process_attachments(files_data: list, username: str) -> list:
    attachments = []
    for file_info in files_data:
        file_name = file_info.get("name")
        file_type = file_info.get("type", "")
        file_size = file_info.get("size", 0)
        file_data = file_info.get("data")

        if not file_data:
            logger.log_warning(f"No data for attachment '{file_name}'")
            return attachments

        try:
            # Extract base64 data
            encoded = file_data.split(",")[1] if "," in file_data else file_data
            file_bytes = base64.b64decode(encoded)

            # Save file
            file_uuid = str(uuid.uuid4())
            new_filename = f"{file_uuid}_{file_name}"
            file_path = os.path.join(ATTACHMENT, new_filename)

            with open(file_path, "wb") as f:
                f.write(file_bytes)

            base_url = os.getenv("BASE_URL", "http://45.248.33.189:8100")
            file_url = f"{base_url}/api/a/{new_filename}"

            attachments.append(
                {
                    "name": file_name,
                    "url": file_url,
                    "type": file_type,
                    "size": file_size,
                }
            )

            logger.log_info(f"Saved attachment: {file_url}")

        except Exception as e:
            logger.log_error(f"Error processing file '{file_name}': {e}")

    return attachments


def check_for_prospective_chat(sender: str, reciever: str, db: Session):
    sender_user = db.query(models.User).filter(models.User.uuid == sender).first()
    reciever_user = db.query(models.User).filter(models.User.uuid == reciever).first()

    client_user = provider_user = None
    if sender_user.role_type == "service_provider":
        provider_user = sender_user
    if reciever_user.role_type == "service_provider":
        provider_user = reciever_user
    if sender_user.role_type == "client":
        client_user = sender_user
    if reciever_user.role_type == "client":
        client_user = reciever_user
    if not client_user or not provider_user:
        return False, None, None
    if (
        client_user.approved_by == provider_user.uuid
        or client_user.created_by == provider_user.uuid
    ):
        return False, None, None

    membership = (
        db.query(models.Membership).filter(
            and_(
                models.Membership.uuid == provider_user.uuid,
                or_(
                    models.Membership.status == "active",
                    models.Membership.status == "trial",
                ),
            )
        )
    ).first()

    if not membership:
        raise LookupError("Membership record not found.")

    subscription = (
        db.query(models.Subscription)
        .filter(models.Subscription.subscription_id == membership.subscription_id)
        .first()
    )

    if subscription:
        return True, subscription.chat_with_prospective_clients, provider_user.uuid

    return True, True, ""


async def get_or_create_chat(
    db: Session, sender: str, receiver: str, message: str
) -> models.Chat:
    # Find existing chat
    chat = (
        db.query(models.Chat)
        .filter(
            ((models.Chat.sender_id == sender) & (models.Chat.receiver_id == receiver))
            | (
                (models.Chat.sender_id == receiver)
                & (models.Chat.receiver_id == sender)
            )
        )
        .first()
    )

    if not chat:
        chat = models.Chat(sender_id=sender, receiver_id=receiver, message=message)
        db.add(chat)
        db.commit()
        db.refresh(chat)
        logger.log_info(f"New chat created: {chat.chat_id}")

    return chat


async def save_message(
    db: Session, chat_id: str, sender: str, message: str, attachments: list
):
    new_message = models.Message(
        chat_id=chat_id, sender_id=sender, message=message, attachment=attachments
    )
    db.add(new_message)

    # Update chat timestamp
    chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
    if chat:
        chat.updated_at = datetime.now()

    db.commit()
    logger.log_info(f"Message saved in chat {chat_id}")


async def notify_chat_participants(chat: models.Chat, message: str):
    for participant in [str(chat.sender_id), str(chat.receiver_id)]:
        if participant in clients:
            logger.log_info(f"Notifying participant {participant}")
            await clients[participant].send_text(message)


async def deliver_message(recipient: str, payload: dict, websocket: WebSocket):
    if recipient in clients:
        logger.log_info(f"Sending to {recipient}")
        await clients[recipient].send_text(json.dumps(payload))
    else:
        logger.log_warning(f"{recipient} not connected")
        await websocket.send_text(f"{recipient} is offline")


@router.post("/chats")
async def start_chat(chat: schemas.ChatCreate, db: Session = Depends(get_db)):
    # Check if a chat session between these two users already exists
    existing_chat = (
        db.query(models.Chat)
        .filter(
            (
                (models.Chat.sender_id == chat.sender_id)
                & (models.Chat.receiver_id == chat.receiver_id)
            )
            | (
                (models.Chat.sender_id == chat.receiver_id)
                & (models.Chat.receiver_id == chat.sender_id)
            )
        )
        .first()
    )

    sender = db.query(models.User).filter(models.User.uuid == chat.sender_id).first()
    sender_name = None

    if sender:
        role = sender.role_type
        if role in [
            "admin",
            "service_provider",
            "sub_admin",
            "sub_service_provider",
            "client",
        ]:
            sender_name = sender.details.get(role, {}).get(
                "name"
            ) or sender.details.get(role, {}).get(
                "first_name", ""
            ) + " " + sender.details.get(role, {}).get("last_name", "")

    # If an existing chat exists but was either deleted or ended, create a new chat with a new chat ID
    if existing_chat and (existing_chat.is_deleted or existing_chat.end_chat):
        new_chat = models.Chat(
            sender_id=chat.sender_id,
            receiver_id=chat.receiver_id,
            message=chat.message,
            is_deleted=False,  # Ensure the new chat is active
            end_chat=False,  # Ensure the new chat is not ended
            deleted_at=None,  # Reset deleted timestamp if applicable
        )
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat

    # If a chat already exists and is active, return it
    if existing_chat:
        return existing_chat

    # If no chat exists at all, create a new one
    new_chat = models.Chat(
        sender_id=chat.sender_id, receiver_id=chat.receiver_id, message=chat.message
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)

    # Create a notification for the receiver
    notification = models.Notification(
        user_id=chat.receiver_id,
        title="Start Chat",
        message=f"Start chat with {chat.message}",
        is_read=False,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    # Send real-time notification via WebSocket
    await manager.send_to_user(
        chat.receiver_id,
        {
            "type": "CHAT_REQUEST",
            "chat_id": str(new_chat.chat_id),
            "sender_id": chat.sender_id,
            "sender_name": sender_name,
            "message": chat.message,
        },
    )

    return new_chat


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ATTACHMENT = os.path.join(BASE_DIR, "attachments")
os.makedirs(ATTACHMENT, exist_ok=True)


def save_uploaded_pdf(
    file: UploadFile, request: Request, folder: str | None = None
) -> dict | None:
    if not file:
        return None
    folder = folder or ATTACHMENT  # Default folder for attachments
    file_uuid = str(uuid.uuid4())
    new_filename = f"{file_uuid}_{file.filename}"
    file_path = os.path.join(folder, new_filename)

    try:
        # Save file bytes to disk
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        # Get the file size from disk
        size = os.path.getsize(file_path)
        # Determine base URL: use BASE_URL environment variable if set; otherwise, use request.base_url.
        base_url = os.environ.get("BASE_URL", str(request.base_url)).rstrip("/")
        file_url = f"{base_url}/api/a/{new_filename}"
        return {"url": file_url, "size": size}
    except Exception as e:
        logger.log_error(f"Error saving PDF file: {e}")
        return None


@router.post("/messages", response_model=schemas.Message)
async def send_message(
    request: Request,
    chat_id: int = Form(...),
    sender_id: UUID4 = Form(...),
    message_text: str | None = Form(None),
    files: List[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    # Filter out empty file entries
    files = [file for file in files if file.filename]
    # Validate chat exists
    chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Validate sender exists
    sender = db.query(models.User).filter(models.User.uuid == sender_id).first()
    if not sender:
        raise HTTPException(status_code=404, detail="Sender not found")

    # Create new message record with empty attachments list by default
    new_message = models.Message(
        chat_id=chat_id,
        sender_id=sender_id,
        message=message_text,
        attachment=[],
    )

    # Process attachments if provided
    if files:
        attachments = []
        for file in files:
            file_info = save_uploaded_pdf(file, request)
            if file_info:
                attachments.append(
                    {
                        "name": file.filename,
                        "url": file_info["url"],
                        "type": file.content_type,
                        "size": file_info["size"],
                    }
                )
        new_message.attachment = attachments

    db.add(new_message)
    chat.updated_at = datetime.now()
    db.commit()
    db.refresh(new_message)

    return new_message


@router.put("/messages/{message_id}/read")
def mark_message_as_read(message_id: int, db: Session = Depends(get_db)):
    message = (
        db.query(models.Message).filter(models.Message.message_id == message_id).first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    message.is_read = True
    db.commit()
    db.refresh(message)
    return message


@router.put("/messages/{chat_id}/read_all")
def mark_all_messages_as_read(chat_id: int, db: Session = Depends(get_db)):
    all_messages = (
        db.query(models.Message).filter(models.Message.chat_id == chat_id).all()
    )
    for message in all_messages:
        message.is_read = True
    db.commit()  # Commit the changes for all messages
    # Refresh each message individually if needed
    for message in all_messages:
        db.refresh(message)
    return all_messages


@router.get("/messages/{chat_id}", response_model=List[schemas.MessageResponse])
def get_messages(chat_id: int, db: Session = Depends(get_db)):
    # Fetch chat details
    chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get sender and receiver from correct fields
    sender_id, receiver_id = chat.sender_id, chat.receiver_id

    # Fetch receiver's email
    receiver = (
        db.query(models.User.useremail).filter(models.User.uuid == receiver_id).first()
    )
    receiver_email = receiver.useremail if receiver else None  # Handle missing user

    # Fetch messages along with sender's profile_img
    messages = (
        db.query(
            models.Message.message_id,  # Add message_id
            models.Message.chat_id,
            models.Message.sender_id,
            models.Message.message,
            models.Message.attachment,
            models.Message.sent_at,  # Add sent_at
            models.User.profile_img,
        )
        .outerjoin(models.User, models.User.uuid == models.Message.sender_id)
        .filter(models.Message.chat_id == chat_id)
        .order_by(models.Message.sent_at)
        .all()
    )

    # Modify the return response to include message_id and sent_at
    return [
        {
            "message_id": msg.message_id,  # Include message_id
            "chat_id": msg.chat_id,
            "sender_id": msg.sender_id,
            "message": msg.message,
            "attachment": msg.attachment,
            "profile_img": msg.profile_img,
            "receiver_email": receiver_email,
            "sent_at": msg.sent_at,  # Include sent_at
        }
        for msg in messages
    ]


@router.get("/chats/user/{user_id}")
def get_user_chats(
    user_id: UUID4, name: str | None = None, db: Session = Depends(get_db)
):
    """
    Returns all chat sessions in which the given user participates.
    Optionally filters chats based on the other user's first or last name.
    """
    # Query to get the chat sessions, excluding ended chats and those where user_id is in deleted_by
    chat_sessions = (
        db.query(models.Chat)
        .filter(
            or_(models.Chat.sender_id == user_id, models.Chat.receiver_id == user_id),
            models.Chat.end_chat == False,  # Exclude ended chats
            ~models.Chat.deleted_by.any(
                user_id
            ),  # Ensure user_id is NOT in deleted_by list
        )
        .order_by(
            models.Chat.updated_at.desc()
        )  # Sort by updated timestamp in descending order
        .all()
    )
    results = []
    for chat in chat_sessions:
        # Determine the "other" user's ID.
        other_user_id = (
            chat.receiver_id if chat.sender_id == user_id else chat.sender_id
        )

        # Retrieve the other user's record.
        other_user = (
            db.query(models.User).filter(models.User.uuid == other_user_id).first()
        )
        sender = db.query(models.User).filter(models.User.uuid == user_id).first()

        if not other_user:
            logger.log_warning(
                f"No user found for ID {other_user_id}; skipping chat {chat.chat_id}."
            )
            continue

        sender_role_type = sender.role_type if sender else None
        receiver_role_type = other_user.role_type if other_user else None

        # Build the other user's name based on their role.
        user_lat = user_long = user_region = ""
        try:
            if other_user.role_type == "client":
                other_user_name = other_user.details.get("client", {}).get(
                    "first_name", ""
                )
                user_lat = other_user.details.get("client", {}).get(
                    "lat", ""
                )
                user_long = other_user.details.get("client", {}).get(
                    "long", ""
                )
                user_region = other_user.details.get("client", {}).get(
                    "region", ""
                )
            elif other_user.role_type == "service_provider":
                other_user_name = other_user.details.get("service_provider", {}).get(
                    "name", ""
                )
                user_lat = other_user.details.get("service_provider", {}).get(
                    "lat", ""
                )
                user_long = other_user.details.get("service_provider", {}).get(
                    "long", ""
                )
                user_region = other_user.details.get("service_provider", {}).get(
                    "region", ""
                )
            elif other_user.role_type == "sub_admin":
                first = other_user.details.get("sub_admin", {}).get("first_name", "")
                last = other_user.details.get("sub_admin", {}).get("last_name", "")
                other_user_name = f"{first} {last}".strip()
            else:
                other_user_name = other_user.details.get("admin", {}).get("name", "")
        except Exception as e:
            logger.log_error(f"Error retrieving name for user {other_user_id}: {e}")
            other_user_name = None

        # If a search filter is provided, check whether the other user's name contains it.
        if name and name.lower() not in (other_user_name or "").lower():
            logger.log_info(
                f"Chat {chat.chat_id} filtered out because '{name}' not in '{other_user_name}'."
            )
            continue

        other_user_profile_img = other_user.profile_img

        # Get the last message for preview.
        last_message = (
            db.query(models.Message)
            .filter(models.Message.chat_id == chat.chat_id)
            .order_by(models.Message.sent_at.desc())
            .first()
        )

        # Count unread messages from the other user.
        unread_count = (
            db.query(models.Message)
            .filter(
                models.Message.chat_id == chat.chat_id,
                models.Message.sender_id != user_id,
                models.Message.is_read == False,
            )
            .count()
        )

        membership_obj = db.query(models.Membership).filter(and_(models.Membership.uuid == other_user_id, or_(models.Membership.status == "active", models.Membership.status == "trial"))).first()

        if membership_obj:
            subscription_obj = db.query(models.Subscription).filter(models.Subscription.subscription_id == membership_obj.subscription_id).first()

        results.append(
            {
                "chat_id": chat.chat_id,
                "other_user_id": other_user_id,
                "other_user_name": other_user_name,
                "other_user_lat": user_lat,
                "other_user_long": user_long,
                "other_user_region": user_region,
                "profile_img": other_user_profile_img,
                "sender_role_type": sender_role_type,
                "receiver_role_type": receiver_role_type,
                "last_message": last_message.message if last_message else None,
                "unread_count": unread_count,
                "updated_at": chat.updated_at.astimezone().isoformat(),
                "subscription_id": membership_obj.subscription_id if membership_obj else "",
                "view_other_client": subscription_obj.view_other_client if subscription_obj else "",
                "chat_with_prospective_clients": subscription_obj.chat_with_prospective_clients if subscription_obj else ""
            }
        )
        logger.log_info(
            f"Including chat {chat.chat_id} with other user {other_user_id} named '{other_user_name}'."
        )

    logger.log_info(
        f"Total chats returned for user {user_id} with filter '{name}': {len(results)}"
    )
    return results


@router.get("/media/{chat_id}", response_model=List[schemas.MediaResponse])
def get_media(chat_id: int, db: Session = Depends(get_db)):
    # Verify that the chat exists
    chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Retrieve all messages for the chat
    # messages = db.query(models.Message).filter(models.Message.chat_id == chat_id).all()
    messages = (
        db.query(models.Message)
        .filter(
            models.Message.chat_id == chat_id,
            models.Message.is_deleted == False,  # Exclude deleted messages
        )
        .all()
    )

    media_items = []
    for message in messages:
        # Each message.attachment is now a list of dicts
        if message.attachment:
            for att in message.attachment:
                media_items.append(
                    {
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "attachment": att.get("url", ""),
                        "attachment_type": att.get("type", ""),
                        "name": att.get("name", ""),
                        "size": att.get("size", 0),
                        "sent_at": message.sent_at,
                    }
                )

    return media_items


@router.post("/endchat/{chat_id}")
def end_chat(
    chat_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """
    Ends a chat by marking it as ended, sending an email transcript
    to both participants, and updating the UI in real time via WebSocket.
    """
    chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    sender = db.query(models.User).filter(models.User.uuid == chat.sender_id).first()
    receiver = (
        db.query(models.User).filter(models.User.uuid == chat.receiver_id).first()
    )

    if not sender or not receiver:
        raise HTTPException(status_code=404, detail="Sender or receiver not found.")

    sender_email = sender.details.get(sender.role_type, {}).get(
        "email", sender.useremail
    )
    receiver_email = receiver.details.get(receiver.role_type, {}).get(
        "email", receiver.useremail
    )

    # Retrieve all messages for this chat in chronological order
    messages = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat_id)
        .order_by(models.Message.sent_at.asc())
        .all()
    )

    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this chat.")

    # Generate chat transcript
    transcript_lines = [
            "=" * 28,
            f"  Chat Transcript Summary",
            f"  Chat ID: {chat_id}",
            "=" * 28,
            ""
        ]
    for msg in messages:
        sent_time = msg.sent_at.strftime("[%Y-%m-%d %H:%M:%S]")

        sender_name = ""
        if msg.sender_id == sender.uuid:
            sender_name = sender.details.get(sender.role_type, {}).get("first_name") or \
                        sender.details.get(sender.role_type, {}).get("name", "")
        else:
            sender_name = receiver.details.get(receiver.role_type, {}).get("first_name") or \
                        receiver.details.get(receiver.role_type, {}).get("name", "")

        sender_name = sender_name.strip() or "Unknown"
        text = msg.message or ""

        transcript_lines.append(f"{sent_time} {sender_name}: {text}")

        # Add attachment details if any
        if msg.attachment:
            if isinstance(msg.attachment, list) and msg.attachment and isinstance(msg.attachment[0], dict):
                attachments_str = "\n".join([
                    f" - {att.get('name', 'unknown')} ({att.get('url', '')})"
                    for att in msg.attachment
                ])
            else:
                attachments_str = "\n".join([f" - {a}" for a in msg.attachment])

            transcript_lines.append("Attachments:\n" + attachments_str)

        transcript_lines.append("")

    transcript = "\n".join(transcript_lines)

    # Mark chat as ended
    chat.end_chat = True  
    chat.updated_at = datetime.now()

    db.commit()

    # Send chat transcript emails
    subject = "Chat Transcript from Hope For Everybody Platform"
    print(transcript)
    body = templates.get_template("chatranscript.html").render(
            chat_id = chat_id,
            transcript_content = transcript,
            website_link = os.getenv("BASE_URL"),
            support_email = os.getenv("SUPPORT_EMAIL")
        )
    print(body)
    background_tasks.add_task(send_email, sender_email, subject, body)
    background_tasks.add_task(send_email, receiver_email, subject, transcript)

    # WebSocket message to update UI live
    update_message = json.dumps({"event": "chat_ended", "chat_id": chat_id})

    # Send WebSocket update if clients are connected
    if chat.sender_id in clients:
        asyncio.create_task(clients[chat.sender_id].send_text(update_message))

    if chat.receiver_id in clients:
        asyncio.create_task(clients[chat.receiver_id].send_text(update_message))

    return {
        "detail": f"Chat {chat_id} has been ended. Transcript sent to {sender_email} and {receiver_email}.",
        "sender_email": sender_email,
        "receiver_email": receiver_email,
    }


@router.delete("/delete-chat/{chat_id}")
def delete_chat(
    chat_id: int, user: schemas.DeleteChatUser, db: Session = Depends(get_db)
):
    chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()

    if not chat:
        return JSONResponse(status_code=404, content={"message": "Chat not found"})

    # Ensure deleted_by is a list and append the user_id
    if chat.deleted_by is None:
        chat.deleted_by = []
    elif not isinstance(chat.deleted_by, list):
        chat.deleted_by = [chat.deleted_by]

    # Append user_id if not already in the list
    user_uuid_str = str(user.user_id)
    if user_uuid_str not in chat.deleted_by:
        chat.deleted_by.append(user_uuid_str)

    # Soft delete chat
    chat.is_deleted = True
    chat.deleted_at = datetime.now()

    # Update the chat record with new deleted_by list
    db.query(models.Chat).filter(models.Chat.chat_id == chat_id).update(
        {
            "is_deleted": True,
            "deleted_at": datetime.now(),
            "deleted_by": chat.deleted_by,
        }
    )

    db.commit()

    # Soft delete associated messages
    db.query(models.Message).filter(models.Message.chat_id == chat_id).update(
        {"is_deleted": True, "deleted_at": datetime.now()}
    )

    db.commit()

    return {
        "detail": f"Chat with ID {chat_id} is marked as deleted successfully by user {user.user_id}"
    }


class NotificationManager:
    def __init__(self):
        self.active_connections: dict[
            str, WebSocket
        ] = {}  # Store connections by user ID

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.log_info(
            f"[WebSocket] User {user_id} connected. Active connections: {list(self.active_connections.keys())}"
        )

    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.log_info(
                f"[WebSocket] User {user_id} disconnected. Active connections: {list(self.active_connections.keys())}"
            )

    async def send_to_user(self, user_id: str, message: str):
        connection = self.active_connections.get(user_id)
        if connection:
            try:
                await connection.send_text(message)
                logger.log_info(f"[WebSocket] Sent to user {user_id}: {message}")
            except Exception as e:
                logger.log_error(f"[WebSocket] Error sending to {user_id}: {e}")
                await self.disconnect(user_id)
        else:
            logger.log_warning(
                f"[WebSocket] User {user_id} is not connected. Message not sent: {message}"
            )

    async def is_connected(self, user_id: str):
        return user_id in self.active_connections


manager = NotificationManager()


@router.websocket("/ws/notifications/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    db = next(get_db())  # Get DB session
    await manager.connect(user_id, websocket)

    # Initialize a counter for the messages received.
    message_count = 0

    try:
        while True:
            data = await websocket.receive_json()
            message_count += 1  # Increment counter for each message received.
            logger.log_info(
                f"[WebSocket]============== Message #{message_count} received from '{user_id}': {data}"
            )

            msg_type = data.get("type")

            # Handle broadcast notifications separately
            if msg_type == "BROADCAST_NOTIFICATION_SEND":
                recipients = data.get("recipients", [])
                message = data.get("message", "")

                if not recipients or not message:
                    await websocket.send_json(
                        {"type": msg_type, "error": "Missing recipients or message"}
                    )
                    continue

                try:
                    # Send real-time notification via WebSocket
                    for recipient in recipients:
                        await manager.send_to_user(
                            str(recipient),
                            json.dumps(
                                {
                                    "type": msg_type,
                                    "recipient": recipient,
                                    "message": message,
                                }
                            ),
                        )
                except Exception as e:
                    logger.log_error(
                        f"Failed to send WebSocket message to {recipient}: {e!s}"
                    )

                db.commit()
                await websocket.send_json(
                    {"type": msg_type, "status": "Broadcast sent successfully"}
                )

            elif msg_type == "New_Provider_SignUp_Notification":
                admins = (
                    db.query(models.User).filter(models.User.role_type == "admin").all()
                )
                for admin in admins:
                    admin_id_str = str(admin.uuid)
                    logger.log_info(f"Sending payload to recipient '{admin.uuid}'.")
                    await manager.send_to_user(
                        str(admin_id_str),
                        json.dumps(
                            {
                                "type": "New_Provider_SignUp_Notification",
                            }
                        ),
                    )
            else:
                client_id = data.get("client_id")
                provider_id = data.get("provider_id")
                if not client_id or not provider_id:
                    logger.log_warning(
                        f"[WebSocket] Invalid message data from '{user_id}': {data}"
                    )
                    await websocket.send_json(
                        {"type": msg_type, "error": "Missing client_id or provider_id"}
                    )
                    continue

                if msg_type == "SEND_REQUEST_NOTIFY":
                    client_user = (
                        db.query(models.User)
                        .filter(models.User.uuid == client_id)
                        .first()
                    )
                    if not client_user:
                        await websocket.send_json(
                            {"type": msg_type, "error": "Client not found"}
                        )
                        continue

                    client_details = client_user.details.get("client", {})
                    client_first_name = client_details.get("first_name", "Unknown")
                    client_last_name = client_details.get("last_name", "Unknown")

                    if await manager.is_connected(provider_id):
                        await manager.send_to_user(
                            provider_id,
                            json.dumps(
                                {
                                    "type": msg_type,
                                    "message": f"New Request: {client_first_name} {client_last_name} wants to connect with you.",
                                }
                            ),
                        )
                    else:
                        logger.log_warning(
                            f"[WebSocket] Provider {provider_id} is not connected."
                        )

                elif msg_type in ("ACCEPT_REQUEST_NOTIFY", "ACCEPT_REQUEST"):
                    provider_user = (
                        db.query(models.User)
                        .filter(models.User.uuid == provider_id)
                        .first()
                    )
                    if not provider_user:
                        await websocket.send_json(
                            {"type": msg_type, "error": "Provider not found"}
                        )
                        continue

                    provider_details = provider_user.details.get("service_provider", {})
                    provider_name = provider_details.get("name", "Unknown")

                    if await manager.is_connected(client_id):
                        await manager.send_to_user(
                            client_id,
                            json.dumps(
                                {
                                    "type": msg_type,
                                    "message": f"Your request has been accepted by {provider_name}.",
                                }
                            ),
                        )
                    else:
                        logger.log_warning(
                            f"[WebSocket] Client {client_id} is not connected."
                        )

                elif msg_type in ("REJECT_REQUEST_NOTIFY", "REJECT_REQUEST"):
                    provider_user = (
                        db.query(models.User)
                        .filter(models.User.uuid == provider_id)
                        .first()
                    )
                    if not provider_user:
                        await websocket.send_json(
                            {"type": msg_type, "error": "Provider not found"}
                        )
                        continue

                    provider_details = provider_user.details.get("provider", {})
                    provider_name = provider_details.get("name", "Unknown")

                    if await manager.is_connected(client_id):
                        await manager.send_to_user(
                            client_id,
                            json.dumps(
                                {
                                    "type": msg_type,
                                    "message": f"Your request was rejected by {provider_name}.",
                                }
                            ),
                        )
                    else:
                        logger.log_warning(
                            f"[WebSocket] Client {client_id} is not connected."
                        )
                else:
                    logger.log_warning(f"[WebSocket] Unknown message type: {msg_type}")

    except Exception as e:
        logger.log_error(f"[WebSocket] Exception: {e!s}")
    finally:
        logger.log_info(f"[WebSocket] Disconnecting WebSocket for user: {user_id}")
        await manager.disconnect(user_id)


@router.post("/notifications/")
async def create_notification(
    notification: schemas.NotificationCreate, db: Session = Depends(get_db)
):
    new_notification = models.Notification(
        user_id=notification.user_id,  # Store user ID
        # title=notification.title,
        message=notification.message,
        is_read=False,
    )
    db.add(new_notification)
    db.commit()
    db.refresh(new_notification)

    # ✅ Send notification only to the intended user
    # await manager.send_to_user(notification.user_id, f"New Notification: {notification.message}")

    return {"message": "Notification sent and stored.", "data": new_notification}


@router.get(
    "/notifications/{user_id}"
)  # response_model=list[schemas.NotificationResponse]
def get_notifications(user_id: str, db: Session = Depends(get_db)):
    # Fetch user role_type from the database
    user = db.query(models.User).filter(models.User.uuid == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Define filter conditions based on user role
    if user.role_type == "service_provider":
        notifications = (
            db.query(models.Notification)
            .filter(
                models.Notification.user_id == user_id,
                models.Notification.type.in_(
                    ["SEND_REQUEST_NOTIFY", "BROADCAST_NOTIFICATION_SEND"]
                ),
            )
            .all()
        )
        first_name = user.details.get("client", {}).get("first_name", "")
        last_name = user.details.get("client", {}).get("last_name", "")
        user_name = f"{first_name} {last_name}".strip()

    elif user.role_type == "client":
        notifications = (
            db.query(models.Notification)
            .filter(
                models.Notification.user_id == user_id,
                models.Notification.type.in_(
                    ["ACCEPT_REQUEST", "REJECT_REQUEST", "BROADCAST_NOTIFICATION_SEND"]
                ),
            )
            .all()
        )
        user_name = user.details.get("service_provider", {}).get("name", "")

    else:
        notifications = (
            db.query(models.Notification)
            .filter(models.Notification.user_id == user_id)
            .all()
        )
        user_name = ""
    chat_notifications = []
    redis_notifcation_data = get_chat_notifications(user_id)
    for redis_notification in redis_notifcation_data:
        user_obj = db.query(models.User).filter(
            models.User.uuid == redis_notification["sender_id"]
        ).first()
        first_name = user_obj.details.get('client').get('first_name', '') 
        last_name = user_obj.details.get('client').get('last_name', '')
        user_name = f"{first_name} {last_name}".strip()
        chat_notifications.append(
            {
                "notification_id": redis_notification.get("notification_id", ""),
                "user_id": redis_notification["sender_id"],
                "title": "",
                "message": redis_notification["message"],
                "is_read": False,
                "created_at": redis_notification["send_time"],
                "updated_at": redis_notification["send_time"],
                "type": "MESSAGE",
            }
        )
    notifications.extend(chat_notifications)
    notifications_response = []
    for notification in notifications:
        if not isinstance(notification, dict):
            notif_dict = notification.__dict__.copy()
        else:
            notif_dict = notification
        notif_dict.pop("_sa_instance_state", None)
        notif_dict["user_name"] = user_name
        if notif_dict['type'] == 'New_Provider_SignUp_Notification':
            notif_dict['user_id'] = notif_dict['title'].split("_")[-1]
            notif_dict['title'] = notif_dict['title'].split("_")[0]
            user_obj = db.query(models.User).filter(
            models.User.uuid == notif_dict['user_id']).first()
            if user_obj:
                notif_dict["profile_img"] = user_obj.profile_img if user_obj.profile_img else ""
        else:
            user_obj = db.query(models.User).filter(
            models.User.uuid == notif_dict['user_id']).first()
            notif_dict["profile_img"] = user_obj.profile_img if user_obj.profile_img else ""
        notifications_response.append(notif_dict)
    return notifications_response


# ✅ Mark a notification as read
@router.put("/notifications/{notification_id}/read")
def mark_as_read(notification_id: str, db: Session = Depends(get_db)):
    try:
        if not notification_id.startswith("r"):
            notification_id = int(notification_id)
            notification = (
                db.query(models.Notification)
                .filter_by(notification_id=notification_id)
                .first()
            )
            if not notification:
                return {"error": "Notification not found"}

            notification.is_read = True
            notification.updated_at = datetime.now()
            db.commit()

            # If is_read is True, delete the notification
            db.delete(notification)
            db.commit()
            return {"message": "Notification marked as read and deleted"}
        else:
            return remove_notifications_on_read(notification_id)
    except Exception as e:
        logger.log_error(f"Error at marking notification as read. Msg->{e}")
        return {"message": "Error at marking notification as read."}


@router.delete("/notifications")
def delete_all_notifications(user_id: UUID4, db: Session = Depends(get_db)):
    try:
        remove_notifications_for_user(str(user_id))
        # Query notifications for the given user_id
        notifications = (
            db.query(models.Notification)
            .filter(models.Notification.user_id == user_id)
            .all()
        )

        if not notifications:
            raise HTTPException(
                status_code=404, detail="No notifications found for the user"
            )

        # Delete all notifications
        db.query(models.Notification).filter(
            models.Notification.user_id == user_id,
            models.Notification.type != "BROADCAST_NOTIFICATION_SEND",
        ).delete(synchronize_session=False)

        db.commit()
        return {"message": "All notifications deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {e!s}")
