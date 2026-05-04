from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Beer(Base):
    __tablename__ = "beers"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)
    normalized_name = Column(String, index=True)

    brewery = Column(String)
    type = Column(String)

    volume_cl = Column(Float)
    abv = Column(Float)

    image = Column(String)

    fingerprint = Column(String, index=True)
    match_score = Column(Float)   # 🔥 DEN HER

    # 🔥 NY – bruges til stærk matching
    fingerprint = Column(String, index=True)

    prices = relationship("Price", back_populates="beer")
    history = relationship("PriceHistory", back_populates="beer")


class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)

    beer_id = Column(Integer, ForeignKey("beers.id"))

    shop_name = Column(String)
    price_dkk = Column(Float)

    old_price = Column(Float)
    discount_pct = Column(Float)

    url = Column(String)
    available = Column(Boolean)

    beer = relationship("Beer", back_populates="prices")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True)

    beer_id = Column(Integer, ForeignKey("beers.id"))

    price_dkk = Column(Float)
    shop_name = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)

    beer = relationship("Beer", back_populates="history")


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True)

    beer_id = Column(Integer, ForeignKey("beers.id"))

    target_price = Column(Float)
    email = Column(String)

    active = Column(Boolean, default=True)