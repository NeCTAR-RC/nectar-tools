# table_def.py
from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base

engine = create_engine('sqlite:///vm_backup.db', echo=False)
Base = declarative_base()


class VM(Base):

    __tablename__ = "vm_data"
    id = Column(Integer, primary_key=True)
    host = Column(String(10), nullable=False)
    uuid_vm = Column(String(256), nullable=False)
    vm_state = Column(String(20), nullable=False)
    update_state = Column(String(20), nullable=False)

Base.metadata.create_all(engine)
