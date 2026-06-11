from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text, Enum
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class AgentVersion(Base):
    __tablename__ = 'agent_versions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, index=True)
    version_name = Column(String)
    artifact_content = Column(Text) # Prompt text ou link para fine-tuning dataset
    is_control = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

class FeedbackItem(Base):
    __tablename__ = 'feedback_items'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, index=True)
    episode_id = Column(String)
    user_message = Column(Text)
    agent_response = Column(Text)
    context_window = Column(JSON)
    feedback_type = Column(String) # positive, negative, neutral
    applicability_status = Column(String, default='pending') # pending, non_applicable, applicable, mandatory
    is_superuser = Column(Boolean, default=False)
    pm_annotations = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # FK para o experimento que consumiu esse feedback
    experiment_id = Column(String, ForeignKey('experiments.id'), nullable=True)

class Experiment(Base):
    __tablename__ = 'experiments'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, index=True)
    experiment_type = Column(String) # prompt_mutation, fine_tuning
    status = Column(String, default='draft') # draft, running, completed, rolled_back
    metric_to_validate = Column(String)
    rollout_fraction = Column(Float, default=0.1)
    created_at = Column(DateTime, default=func.now())
    
    versions = relationship("AgentVersion", backref="experiment")

class ExperimentResult(Base):
    __tablename__ = 'experiment_results'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String, ForeignKey('agent_versions.id'))
    metric_value = Column(Float)
    session_count = Column(Integer)
    stat_significance_p_value = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=func.now())
