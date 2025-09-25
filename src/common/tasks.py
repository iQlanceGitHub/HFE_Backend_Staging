import datetime
import json

import redis

from src.common.celery_worker import celery_app
from src.configs.config import logger

# Connect to Redis
redis_app = redis.Redis(host="redis", port=6379, db=0, decode_responses=True)


@celery_app.task
def store_notification(user_id: str, message: str, sender_id: str):
    try:
        logger.log_info(
            f"Storing notification for the {user_id} with message {message}"
        )
        key = user_id
        notifications = redis_app.lrange(key, 0, -1)
        logger.log_info(f"Got the {len(notifications)} notifications for the {user_id}")
        data = {
            "notification_id": f"r_{user_id}_{1001 + len(notifications)}",
            "sender_id": sender_id,
            "send_time": datetime.datetime.today().strftime("%Y_%m_%d_%H_%M_%S"),
            "message": message,
        }
        if len(notifications):
            redis_app.delete(key)
            notifications = [json.loads(notification) for notification in notifications]
            notifications.append(data)
        else:
            notifications = [data]
        redis_app.rpush(
            key, *[json.dumps(notification) for notification in notifications]
        )
        logger.log_info(
            f"Successfull stored notification for the {user_id} with data : {data}"
        )
    except Exception as e:
        logger.log_error(f"Error while storing the notification to redi. Msg: {e}")


def get_notifications(user_id: str):
    notification_data = []
    try:
        logger.log_info(f"Getting the stored notification for the {user_id}")
        key = user_id
        notifications = redis_app.lrange(key, 0, -1)
        notification_data = [json.loads(notification) for notification in notifications]
        return notification_data
    except Exception as e:
        logger.log_error(f"Error getting the notification from redis. Msg: {e}")
    return notification_data


def remove_notifications_for_sender(user_id: str, sender_id: str):
    try:
        key = user_id

        notifications = redis_app.lrange(key, 0, -1)
        updated_notifications = []
        logger.log_info(
            f"Removing notifcations for the {user_id} with sender : {sender_id}"
        )

        for notification in notifications:
            data = json.loads(notification)
            if data["sender_id"] != sender_id:
                updated_notifications.append(notification)

        redis_app.delete(key)
        if updated_notifications:
            redis_app.rpush(key, *updated_notifications)
            logger.log_info(
                f"Successfully removed notifcations for the {user_id} with sender : {sender_id}"
            )

        logger.log_info(
            f"Removed notifications for sender {sender_id} from user {user_id}."
        )
    except Exception as e:
        logger.log_error(f"Error removing the notification from redis. Msg: {e}")


def remove_notifications_on_read(notification_id):
    try:
        key = notification_id.split("_")[1]

        notifications = redis_app.lrange(key, 0, -1)
        updated_notifications = []
        logger.log_info(
            f"Removing notifcations for the {key} with notifcation_id : {notification_id}"
        )

        for notification in notifications:
            data = json.loads(notification)
            if data.get("notification_id", "") != notification_id:
                updated_notifications.append(notification)

        redis_app.delete(key)
        if updated_notifications:
            redis_app.rpush(key, *updated_notifications)

        logger.log_info(
            f"Removed notifications {notification_id} on marked for from redis."
        )
        return {"message": "Notification marked as read and deleted"}
    except Exception as e:
        logger.log_error(
            f"Error removing the notification on marked read from redis. Msg: {e}"
        )
        return {"message": "Error on marking meesage notification as read."}


def remove_notifications_for_user(user_id):
    try:
        redis_app.delete(user_id)
        logger.log_info(f"Removed all notifications {user_id}.")
    except Exception as e:
        logger.log_error(f"Error on deleteing the notification. Msg: {e}")
