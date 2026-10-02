from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(160), default="")
    language: Mapped[str] = mapped_column(String(2), default="ru")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Administrator(Base):
    __tablename__ = "administrators"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Car(Base):
    __tablename__ = "cars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    make_model: Mapped[str] = mapped_column(String(180), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), index=True)
    mileage: Mapped[int] = mapped_column(Integer)
    fuel_type: Mapped[str] = mapped_column(String(24), index=True)
    transmission: Mapped[str] = mapped_column(String(24), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="available", index=True)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    photos: Mapped[list["CarPhoto"]] = relationship(
        back_populates="car", cascade="all, delete-orphan", order_by="CarPhoto.position"
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )
    viewing_requests: Mapped[list["ViewingRequest"]] = relationship(
        back_populates="car", cascade="all, delete-orphan"
    )


class CarPhoto(Base):
    __tablename__ = "car_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(String(256))
    position: Mapped[int] = mapped_column(Integer, default=0)

    car: Mapped[Car] = relationship(back_populates="photos")


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    car: Mapped[Car] = relationship(back_populates="favorites")


class ViewingRequest(Base):
    __tablename__ = "viewing_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True
    )
    car_id: Mapped[int] = mapped_column(
        ForeignKey("cars.id", ondelete="CASCADE"), index=True
    )
    preferred_time: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    car: Mapped[Car] = relationship(back_populates="viewing_requests")
