from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models.base import Base, Agent, Feedback
from datetime import datetime

DATABASE_URL = "sqlite:///./darwin.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="DarwinLoop Backend")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/api/v1/feedback")
def receive_feedback(feedback_data: dict, db: Session = Depends(get_db)):
    # Aqui entra o processamento e salvamento
    new_feedback = Feedback(
        agent_id=feedback_data['agent_id'],
        trace_id=feedback_data['trace_id'],
        score=feedback_data['score'],
        signal_type=feedback_data.get('signal_type', 'neutral'),
        context_window=feedback_data['context_window']
    )
    db.add(new_feedback)
    db.commit()
    return {"status": "success"}

@app.get("/api/v1/feedbacks")
def list_feedbacks(agent_id: str = None, db: Session = Depends(get_db)):
    query = db.query(Feedback)
    if agent_id:
        query = query.filter(Feedback.agent_id == agent_id)
    return query.all()

@app.get("/api/v1/agents")
def list_agents(db: Session = Depends(get_db)):
    return db.query(Agent).all()
