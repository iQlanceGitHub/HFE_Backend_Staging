from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import SignUpDocumentCreate, SignUpDocumentType
from src.configs.config import logger
from src.models.models import SignUpDocuments


def get_document(db: Session, doc_type: str):
    logger.log_info(f"Getting Sigup Doc data for {doc_type}")
    valid_types = {dt.value for dt in SignUpDocumentType}
    if doc_type not in valid_types:
        logger.log_info(
            f"Invalid document type. Must be one of: {', '.join(valid_types)}"
        )
    return (
        db.query(SignUpDocuments)
        .filter(SignUpDocuments.document_type == doc_type)
        .first()
    )


def create_document(db: Session, document: SignUpDocumentCreate):
    logger.log_info("Creating Sigup Doc data.")
    valid_types = {dt.value for dt in SignUpDocumentType}
    if document.document_type not in valid_types:
        logger.log_info(
            f"Invalid document type. Must be one of: {', '.join(valid_types)}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Invalid document type. Must be one of: {', '.join(valid_types)}",
        )
    if get_document(db, document.document_type):
        logger.log_info(f"Document with {document.title} already exits.")
        raise HTTPException(
            status_code=404, detail=f"Document with {document.title} already exits."
        )
    db_doc = SignUpDocuments(
        title=document.title,
        content=document.content,
        document_type=document.document_type.value,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


def update_document(db: Session, doc_type: str, document: SignUpDocumentCreate):
    logger.log_info(f"Updating Document with {doc_type}.")
    valid_types = {dt.value for dt in SignUpDocumentType}
    if doc_type not in valid_types:
        logger.log_info(
            f"Invalid document type. Must be one of: {', '.join(valid_types)}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"Invalid document type. Must be one of: {', '.join(valid_types)}",
        )
    db_doc = get_document(db, doc_type)
    if not db_doc:
        logger.log_info(f"No document found for the {doc_type}")
        raise HTTPException(
            status_code=404, detail=f"No document found for the {doc_type}"
        )
    for key, value in document.model_dump().items():
        setattr(db_doc, key, value)
    db.commit()
    db.refresh(db_doc)
    return db_doc
