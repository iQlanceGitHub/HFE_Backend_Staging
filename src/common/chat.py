import asyncio
import base64
import json
import os
import uuid
from datetime import datetime
from typing import Dict

from fastapi import WebSocket
from sqlalchemy.orm import Session

from src.common.tasks import remove_notifications_for_sender, store_notification
from src.configs import database
from src.configs.config import logger
from src.models import models

get_db = database.get_db

# Folder for attachments
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ATTACHMENT = os.path.join(BASE_DIR, "attachments")
os.makedirs(ATTACHMENT, exist_ok=True)


def create_chat_id(recipient: str, username: str, db: Session, message_text: str):
    try:
        chat = models.Chat(
            sender_id=username,
            receiver_id=recipient,
            message=message_text,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        logger.log_info(f"New chat created with chat_id: {chat.chat_id}")
        return chat.chat_id
    except Exception as e:
        logger.log_info(f"Error creating chat for {username} and {recipient}: {e}")
        raise


def get_chat_id(recipient: str, username: str, db: Session, message_text: str):
    try:
        logger.log_info(
            f"No chat_id provided. Looking up chat between '{username}' and '{recipient}'."
        )
        chat = (
            db.query(models.Chat)
            .filter(
                (
                    (models.Chat.sender_id == username)
                    & (models.Chat.receiver_id == recipient)
                )
                | (
                    (models.Chat.sender_id == recipient)
                    & (models.Chat.receiver_id == username)
                )
            )
            .first()
        )
        if not chat:
            logger.log_info("No existing chat found. Creating new chat.")
            return create_chat_id(recipient, username, db, message_text)
        return chat.chat_id
    except Exception as e:
        logger.log_info(
            f"Error fetching chat ID between {username} and {recipient}: {e}"
        )
        raise


def add_message(db: Session, data):
    try:
        new_message = models.Message(
            chat_id=data["chat_id"],
            sender_id=data["sender"],
            message=data["message_text"],
            attachment=data["attachments"],
        )
        db.add(new_message)
        db.commit()
        db.refresh(new_message)
        logger.log_info(
            f"Saved new message in chat {data['chat_id']} with attachments: {data['attachments']}"
        )

        chat_obj = (
            db.query(models.Chat).filter(models.Chat.chat_id == data["chat_id"]).first()
        )
        if chat_obj:
            chat_obj.updated_at = datetime.now()
            db.commit()
            logger.log_info(
                f"Updated chat {data['chat_id']} updated_at to {chat_obj.updated_at}."
            )
    except Exception as e:
        logger.log_info(f"Error adding message to chat {data['chat_id']}: {e}")
        raise


def get_attachments(files_data, username: str):
    attachments = []
    try:
        if files_data:
            logger.log_info(
                f"Processing {len(files_data)} attachment(s) for user '{username}'."
            )
            for file_info in files_data:
                file_name = file_info.get("name")
                file_type = file_info.get("type", "")
                file_size = file_info.get("size", 0)
                file_data = file_info.get("data")  # Expecting base64-encoded string
                logger.log_info(
                    f"Attachment received -> Name: {file_name}, Type: {file_type}, Size: {file_size}"
                )

                if file_data:
                    try:
                        # Remove data URL header if present
                        if "," in file_data:
                            header, encoded = file_data.split(",", 1)
                            logger.log_info(f"Attachment header: {header}")
                        else:
                            encoded = file_data
                        file_bytes = base64.b64decode(encoded)
                        logger.log_info(
                            f"Successfully decoded attachment '{file_name}'."
                        )
                    except Exception as e:
                        logger.log_info(f"Error decoding file '{file_name}': {e}")
                        continue

                    file_uuid = str(uuid.uuid4())
                    new_filename = f"{file_uuid}_{file_name}"
                    file_path = os.path.join(ATTACHMENT, new_filename)
                    try:
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
                        logger.log_info(f"Attachment saved successfully: {file_url}")
                    except Exception as e:
                        logger.log_info(f"Error saving file '{file_name}': {e}")
                        continue
                else:
                    logger.log_warning(
                        f"No file data found for attachment '{file_name}'."
                    )
    except Exception as e:
        logger.log_info(f"Error processing attachments for user '{username}': {e}")
        raise

    # Log attachments list after processing
    logger.log_info(f"Attachments processed: {attachments}")
    return attachments


async def end_chat(db: Session, chat_id, clients: Dict[str, WebSocket]):
    try:
        chat = db.query(models.Chat).filter(models.Chat.chat_id == chat_id).first()
        if not chat:
            logger.log_warning(f"Chat {chat_id} not found.")
            return

        # Mark chat as ended
        chat.end_chat = True
        chat.updated_at = datetime.now()
        db.commit()

        update_message = json.dumps({"event": "chat_ended", "chat_id": chat_id})
        if chat.sender_id in clients:
            logger.log_info(f"Sending chat_ended update to sender {chat.sender_id}")
            asyncio.create_task(clients[chat.sender_id].send_text(update_message))
        if chat.receiver_id in clients:
            logger.log_info(f"Sending chat_ended update to receiver {chat.receiver_id}")
            asyncio.create_task(clients[chat.receiver_id].send_text(update_message))
    except Exception as e:
        logger.log_info(f"Error ending chat {chat_id}: {e}")
        raise


def add_notification(data):
    try:
        logger.log_info(f"Storing notification for the {data['receiver']}")
        store_notification.delay(data["receiver"], data["message_text"], data["sender"])
    except Exception as e:
        logger.log_info(
            f"Error storing notification for receiver {data['receiver']}: {e}"
        )
        raise


async def handle_message(
    websocket: WebSocket,
    message_data: dict,
    username: str,
    clients: Dict[str, WebSocket],
):
    db: Session = next(get_db())
    try:
        recipient = message_data.get("recipient")
        message_text = message_data.get("message", "")
        files_data = message_data.get("files", "")
        chat_id = message_data.get("chat_id", "")
        reciever_active_for = message_data.get("reciever_active_for", "")

        if not recipient or message_text is None:
            logger.log_warning(f"Invalid message data from '{username}'")
            await websocket.send_text("Invalid message data.")
            return

        if not chat_id:
            chat_id = get_chat_id(recipient, username, db, message_text)

        if message_text or files_data:
            attachments = get_attachments(files_data, username)
            data = {
                "sender": username,
                "receiver": recipient,
                "message_text": message_text,
                "attachments": attachments,
                "chat_id": chat_id,
            }
            add_message(db, data)
            add_notification(data)

        if reciever_active_for:
            remove_notifications_for_sender(username, reciever_active_for)

        if message_data.get("type") == "END_CHAT":
            logger.log_info(
                f"END_CHAT event received from '{username}' with payload: {message_data}"
            )
            await end_chat(db, chat_id, clients)

        return {
            "sender": username,
            "receiver": recipient,
            "message": message_text,
            "attachments": attachments,
            "type": "END_CHAT",
        }

    except Exception as e:
        logger.log_info(f"Error handling message from '{username}': {e}")
        await websocket.send_text(
            f"An error occurred while processing your message. Error Msg -> {e}"
        )
    finally:
        db.close()
