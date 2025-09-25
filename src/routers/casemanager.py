
from fastapi import APIRouter,Depends
from src.configs import database
from sqlalchemy.orm import Session
import uuid
from src.configs.database import engine
from sqlalchemy import or_
from sqlalchemy.orm.attributes import flag_modified


from src.api import schemas
from src.models import models
from src.configs.config import logger











get_db = database.get_db

router = APIRouter(prefix="/casemanager", tags=["Case Manager"])

@router.get("/get-clients")
async def get_clients(uuid:str,skip:int = 0,limit:int = 10,search:str = None,db: Session = Depends(get_db)):
    """
    Get all the clients which are not assigned to that service provider
    """
    get_user = db.query(models.User).filter(models.User.uuid == uuid).first()
    
    if get_user is None:
        return {
            "status": 404,
            "message": "User not found"
        }
    
    if get_user.role_type != 'service_provider':
        return {
            "status": 403,
            "message": "You are not a service provider"
        }

    base_query = (
        db.query(models.User)
        .filter(models.User.role_type == 'client',models.User.is_deleted == False,models.User.is_activated == True)
        .filter(
            or_(
                models.User.service_provider_ids == None,
                ~models.User.service_provider_ids.any(uuid)
            )
        ).order_by(models.User.created_at.desc())
        )
    total_clients = base_query.count()

    if search:
        base_query = base_query.filter(
            or_(
                models.User.useremail.ilike(f"%{search}%"),
                models.User.details['client']['first_name'].astext.ilike(f"%{search}%"),
                models.User.details['client']['last_name'].astext.ilike(f"%{search}%"),
                models.User.details['client']['email'].astext.ilike(f"%{search}%")
            )
        )
    clients = base_query.offset(skip).limit(limit).all()

    return {
        "status": 200,
        "message": "Clients fetched successfully",
        "total_clients": total_clients,
        "clients": clients
    }
    
@router.get("/get-all-service-providers")
async def get_all_service_providers(uuid:str,skip:int = 0,limit:int = 10,search:str = None,db: Session = Depends(get_db)):
    """
    Get all the service providers which are not assigned to that client
    """
    get_user = db.query(models.User).filter(models.User.uuid == uuid).first()

    if get_user is None:
        return {
            "status": 404,
            "message": "User not found"
        }
    
    if get_user.role_type != 'client':
        return {
            "status": 403,
            "message": "You are not a client"
        }
    
    associated_providers = get_user.service_provider_ids or []
    
    query = db.query(models.User).filter(models.User.role_type == 'service_provider',models.User.is_deleted == False,models.User.is_activated == True)

    if search:
        query = query.filter(
            or_(
                models.User.useremail.ilike(f"%{search}%"),
                models.User.details['service_provider']['founder_first_name'].astext.ilike(f"%{search}%"),
                models.User.details['service_provider']['founder_last_name'].astext.ilike(f"%{search}%"),
                models.User.details['service_provider']['email'].astext.ilike(f"%{search}%"),
                models.User.details['service_provider']['name'].astext.ilike(f"%{search}%")
        ).order_by(models.User.created_at.desc())
        )
    if associated_providers:
        query = query.filter(~models.User.uuid.in_(associated_providers))
    
    total_count = query.count()
    providers = query.offset(skip).limit(limit).all()

    return {
        "status": 200,
        "message": "Service providers fetched successfully",
        "total_service_providers": total_count,
        "service_providers": providers
    }

@router.post("/assign-clients/{user_id}")
async def add_clients_sp(user_id,data:schemas.AssginClients,db: Session = Depends(get_db)):
    """
    Assign clients to service provider by adding service provider's UUID
    to each client's service_provider_ids array (avoid duplicates).
    """
    user = db.query(models.User).filter(models.User.uuid == user_id).first()
    if not user:
        return {
            "status": 404,
            "message": "User not found"
        }
    if user.role_type == 'sub_admin' and user.permission.get("service_provider").get("case_manager") is False:
        return {
            "status": 403,
            "message": "You don't have permission to assign clients"
        }

    get_sp = db.query(models.User).filter(models.User.uuid == data.uuid).first()
    if get_sp is None:

        return {
            "status": 404,
            "message": "User not found"
        }
    client_count = get_sp.details.get("service_provider", {}).get("client_count", 0)

    if client_count is None:
        client_count = 0
    for client_id in data.clients:
        client_count += 1
        flag_modified(get_sp, "details")
        get_client = db.query(models.User).filter(models.User.uuid == client_id).first()
        if get_client:

            if get_client.service_provider_ids is None:
                get_client.service_provider_ids = []
            sp_ids = list(get_client.service_provider_ids)

            if data.uuid not in sp_ids:
                sp_ids.append(data.uuid)
            get_client.service_provider_ids = sp_ids
            db.commit()
            db.refresh(get_client)
            new_request = models.Request(
                id = uuid.uuid4(),
                client_id = get_client.uuid,
                provider_id = data.uuid,
                status = "approved"
            )
            db.add(new_request)
            db.commit()
    return {  
        "status": 200,
        "message": "Clients assigned successfully"
    }

@router.post("/assign-providers/{user_id}")
async def assign_providers(user_id,data:schemas.AssginProviders,db: Session = Depends(get_db)):
    """
    Assing selected provider to specific client .
    """
    user = db.query(models.User).filter(models.User.uuid == user_id).first()
    if not user:
        return {
            "status": 404,
            "message": "User not found"
        }
    if user.role_type == 'sub_admin' and user.permission.get("client").get("case_manager") is False:
        return {
            "status": 403,
            "message": "You don't have permission to assign providers"
        }
    get_client = db.query(models.User).filter(models.User.uuid == data.uuid,models.User.is_deleted == False,models.User.is_activated == True).first()
    if get_client is None:
        return {
            "status": 404,
            "message": "User not found"
        }
    for provider_id in data.providers:
        get_provider = db.query(models.User).filter(models.User.uuid == provider_id).first()
        client_count = get_provider.details.get("service_provider").get("client_count")
        if client_count is None:
            client_count = 0
        
        client_count = client_count + 1
        get_provider.details["service_provider"]["client_count"] = client_count

        flag_modified(get_provider, "details")
        if get_provider:
            if get_client.service_provider_ids is None:
                get_client.service_provider_ids = []
            sp_ids = list(get_client.service_provider_ids)
            if provider_id not in sp_ids:
                sp_ids.append(provider_id)
            get_client.service_provider_ids = sp_ids
            db.commit()
            db.refresh(get_client)
    return {
        "status": 200,
        "message": "Providers assigned successfully"
    }

@router.post("/remove-clients/{user_id}")
async def remove_clients(user_id,data:schemas.AssginClients,db: Session = Depends(get_db)):
    """
    Remove clients from service provider by removing service provider's UUID
    from each client's service_provider_ids array
    """
    user = db.query(models.User).filter(models.User.uuid == user_id).first()
    if not user:
        return {
            "status": 404,
            "message": "User not found"
        }
    if user.role_type == 'sub_admin' and user.permission.get("service_provider").get("case_manager") is False:
        return {
            "status": 403,
            "message": "You don't have permission to remove clients"
        }

    get_sp = db.query(models.User).filter(models.User.uuid == data.uuid,models.User.is_deleted == False,models.User.is_activated == True).first()
    if get_sp is None:
        return {
            "status": 404,
            "message": "User not found"
        }
    for client_id in data.clients:
        get_client = db.query(models.User).filter(models.User.uuid == client_id).first()
        if get_client:
            sp_ids = list(get_client.service_provider_ids)
            if data.uuid in sp_ids:
                sp_ids.remove(data.uuid)
            get_client.service_provider_ids = sp_ids
            db.commit()
            db.refresh(get_client)
    
    return {
        "status": 200,
        "message": "Clients removed successfully"
    }

@router.post("/remove-providers/{user_id}")
async def remove_providers(user_id,data:schemas.AssginProviders,db: Session = Depends(get_db)):
    """
    Remove providers from client by removing provider's UUID
    from  client's service_provider_ids array
    """
    user = db.query(models.User).filter(models.User.uuid == user_id).first()
    if not user:
        return {
            "status": 404,
            "message": "User not found"
        }
    if user.role_type == 'sub_admin' and user.permission.get("client").get("case_manager") is False:
        return {
            "status": 403,
            "message": "You don't have permission to remove providers"
        }
    get_client = db.query(models.User).filter(models.User.uuid == data.uuid,models.User.is_deleted == False,models.User.is_activated == True).first()
    if get_client is None:
        return {
            "status": 404,
            "message": "User not found"
        }
    sp_ids = list(get_client.service_provider_ids)
    for provider_id in data.providers:
        get_provider = db.query(models.User).filter(models.User.uuid == provider_id).first()
        if get_provider:
            if get_provider.uuid in sp_ids:
                sp_ids.remove(get_provider.uuid)
        get_client.service_provider_ids = sp_ids
        db.commit()
        db.refresh(get_client)
    return {
        "status": 200,
        "message": "Providers removed successfully"
    }
