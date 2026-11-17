"""Distractor tools: plausible but irrelevant to every benchmark task (RULES 29).

They exist to measure how tool selection degrades as the tool list grows (E3). Outputs are
generated from a hash of the tool name and arguments, so they are deterministic and never touch
the network or the world database (RULES 21, 24).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import date, timedelta
from typing import Any, ClassVar

from pydantic import Field

from toolproof.env.tools.base import InvalidArgument, Tool, ToolArgs, ToolContext

DETAILED_SUFFIX = " This tool is not connected to the store's orders, customers or refunds."


def _descriptions(minimal: str, standard: str) -> dict[str, str]:
    return {"minimal": minimal, "standard": standard, "detailed": standard + DETAILED_SUFFIX}


def stable_rng(tool_name: str, args: ToolArgs) -> random.Random:
    payload = json.dumps([tool_name, args.model_dump(mode="json")], sort_keys=True)
    return random.Random(int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 16))


def _reference(prefix: str, rng: random.Random) -> str:
    return f"{prefix}-{rng.randrange(16**6):06X}"


# ------------------------------------------------------------------ args


class CityArgs(ToolArgs):
    city: str = Field(min_length=1, max_length=100)


class TranslateArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=2000)
    target_language: str = Field(min_length=2, max_length=40)


class ConvertCurrencyArgs(ToolArgs):
    amount: float
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)


class TickerArgs(ToolArgs):
    ticker: str = Field(min_length=1, max_length=10)


class CalendarEventArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=200)
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(default="09:00", description="HH:MM, 24-hour")


class PostcodeArgs(ToolArgs):
    postcode: str = Field(min_length=3, max_length=10)


class ExchangeRateArgs(ToolArgs):
    base: str = Field(min_length=3, max_length=3)
    quote: str = Field(min_length=3, max_length=3)


class SummariseArgs(ToolArgs):
    text: str = Field(min_length=1, max_length=10000)
    max_words: int = Field(default=50, ge=5, le=500)


class NewsArgs(ToolArgs):
    topic: str = Field(min_length=1, max_length=100)


class SupplierArgs(ToolArgs):
    product_name: str = Field(min_length=1, max_length=200)


class CourierArgs(ToolArgs):
    pickup_address: str = Field(min_length=5, max_length=300)
    parcel_weight_kg: float = Field(gt=0, le=70)


class HolidayArgs(ToolArgs):
    country: str = Field(min_length=2, max_length=60)
    year: int = Field(ge=2000, le=2100)


class ValidateEmailArgs(ToolArgs):
    address: str = Field(min_length=1, max_length=320)


class CouponArgs(ToolArgs):
    percent_off: int = Field(ge=1, le=90)


class StoreHoursArgs(ToolArgs):
    location: str = Field(min_length=1, max_length=100)


# ------------------------------------------------------------------ tools


class GetWeather(Tool[CityArgs]):
    name = "get_weather"
    args_model = CityArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Get the weather.", "Get the current weather for a city."
    )

    def run(self, ctx: ToolContext, args: CityArgs) -> Any:
        rng = stable_rng(self.name, args)
        return {
            "city": args.city,
            "temperature_c": rng.randint(8, 36),
            "conditions": rng.choice(["sunny", "cloudy", "light rain", "windy", "storms"]),
            "humidity_percent": rng.randint(20, 90),
        }


class TranslateText(Tool[TranslateArgs]):
    name = "translate_text"
    args_model = TranslateArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Translate text.", "Translate text into another language."
    )

    def run(self, ctx: ToolContext, args: TranslateArgs) -> Any:
        return {
            "target_language": args.target_language,
            "translation": f"[{args.target_language}] {args.text}",
        }


class ConvertCurrency(Tool[ConvertCurrencyArgs]):
    name = "convert_currency"
    args_model = ConvertCurrencyArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Convert currency.", "Convert an amount from one currency to another (ISO codes)."
    )

    def run(self, ctx: ToolContext, args: ConvertCurrencyArgs) -> Any:
        rate = round(stable_rng(self.name, args).uniform(0.4, 1.8), 4)
        return {
            "from": args.from_currency.upper(),
            "to": args.to_currency.upper(),
            "rate": rate,
            "converted_amount": round(args.amount * rate, 2),
        }


class GetStockPrice(Tool[TickerArgs]):
    name = "get_stock_price"
    args_model = TickerArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Get a stock price.", "Get the latest share price for a stock ticker."
    )

    def run(self, ctx: ToolContext, args: TickerArgs) -> Any:
        rng = stable_rng(self.name, args)
        return {
            "ticker": args.ticker.upper(),
            "price": round(rng.uniform(2, 400), 2),
            "change_percent": round(rng.uniform(-4, 4), 2),
        }


class CreateCalendarEvent(Tool[CalendarEventArgs]):
    name = "create_calendar_event"
    args_model = CalendarEventArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Create an event.", "Create an event in the team calendar."
    )

    def run(self, ctx: ToolContext, args: CalendarEventArgs) -> Any:
        try:
            date.fromisoformat(args.date)
        except ValueError:
            raise InvalidArgument(f"'{args.date}' is not a date in YYYY-MM-DD format.") from None
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", args.time):
            raise InvalidArgument(f"'{args.time}' is not a time in HH:MM format.")
        return {
            "event_id": _reference("EVT", stable_rng(self.name, args)),
            "title": args.title,
            "date": args.date,
            "time": args.time,
            "status": "created",
        }


class LookupPostcode(Tool[PostcodeArgs]):
    name = "lookup_postcode"
    args_model = PostcodeArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Look up a postcode.", "Look up the suburb and state for a postcode."
    )

    def run(self, ctx: ToolContext, args: PostcodeArgs) -> Any:
        rng = stable_rng(self.name, args)
        return {
            "postcode": args.postcode,
            "suburb": rng.choice(["Riverside", "Hillcrest", "Bayview", "Northgate", "Elmwood"]),
            "state": rng.choice(["NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"]),
        }


class GetExchangeRate(Tool[ExchangeRateArgs]):
    name = "get_exchange_rate"
    args_model = ExchangeRateArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Get an exchange rate.", "Get the exchange rate between two currencies."
    )

    def run(self, ctx: ToolContext, args: ExchangeRateArgs) -> Any:
        return {
            "base": args.base.upper(),
            "quote": args.quote.upper(),
            "rate": round(stable_rng(self.name, args).uniform(0.4, 1.8), 4),
        }


class SummariseText(Tool[SummariseArgs]):
    name = "summarise_text"
    args_model = SummariseArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Summarise text.", "Summarise a piece of text in a given number of words."
    )

    def run(self, ctx: ToolContext, args: SummariseArgs) -> Any:
        words = args.text.split()
        summary = " ".join(words[: args.max_words])
        return {"summary": summary + (" ..." if len(words) > args.max_words else "")}


class GetNews(Tool[NewsArgs]):
    name = "get_news"
    args_model = NewsArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Get news.", "Get recent news headlines about a topic."
    )

    def run(self, ctx: ToolContext, args: NewsArgs) -> Any:
        rng = stable_rng(self.name, args)
        templates = [
            "Analysts discuss the outlook for {t}",
            "New report highlights trends in {t}",
            "Local businesses respond to changes in {t}",
            "What the latest survey says about {t}",
        ]
        rng.shuffle(templates)
        return {"headlines": [template.format(t=args.topic) for template in templates[:3]]}


class CheckInventorySupplier(Tool[SupplierArgs]):
    name = "check_inventory_supplier"
    args_model = SupplierArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Check supplier stock.", "Check how many units an external supplier has of a product."
    )

    def run(self, ctx: ToolContext, args: SupplierArgs) -> Any:
        rng = stable_rng(self.name, args)
        return {
            "product_name": args.product_name,
            "supplier": rng.choice(["Acme Wholesale", "Harbour Supply Co", "Summit Traders"]),
            "units_available": rng.randint(0, 5000),
            "lead_time_days": rng.randint(2, 30),
        }


class BookCourier(Tool[CourierArgs]):
    name = "book_courier"
    args_model = CourierArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Book a courier.", "Book a courier pickup for a parcel."
    )

    def run(self, ctx: ToolContext, args: CourierArgs) -> Any:
        rng = stable_rng(self.name, args)
        return {
            "booking_id": _reference("CR", rng),
            "pickup_date": (ctx.today + timedelta(days=rng.randint(1, 3))).isoformat(),
            "price": round(8 + args.parcel_weight_kg * rng.uniform(1.2, 2.5), 2),
            "status": "booked",
        }


class GetHolidayList(Tool[HolidayArgs]):
    name = "get_holiday_list"
    args_model = HolidayArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "List holidays.", "List the public holidays for a country and year."
    )

    def run(self, ctx: ToolContext, args: HolidayArgs) -> Any:
        return {
            "country": args.country,
            "year": args.year,
            "holidays": [
                {"date": f"{args.year}-01-01", "name": "New Year's Day"},
                {"date": f"{args.year}-12-25", "name": "Christmas Day"},
                {"date": f"{args.year}-12-26", "name": "Boxing Day"},
            ],
        }


class ValidateEmail(Tool[ValidateEmailArgs]):
    name = "validate_email"
    args_model = ValidateEmailArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Validate an email.", "Check whether an email address is formatted correctly."
    )

    def run(self, ctx: ToolContext, args: ValidateEmailArgs) -> Any:
        valid = re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.address.strip()) is not None
        return {"address": args.address, "valid_format": valid}


class GenerateCoupon(Tool[CouponArgs]):
    name = "generate_coupon"
    args_model = CouponArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Make a coupon.", "Generate a discount coupon code for a percentage off."
    )

    def run(self, ctx: ToolContext, args: CouponArgs) -> Any:
        rng = stable_rng(self.name, args)
        return {
            "coupon_code": _reference("SAVE", rng),
            "percent_off": args.percent_off,
            "note": "Coupon codes are not linked to any customer account.",
        }


class GetStoreHours(Tool[StoreHoursArgs]):
    name = "get_store_hours"
    args_model = StoreHoursArgs
    is_distractor = True
    descriptions: ClassVar[dict[str, str]] = _descriptions(
        "Get store hours.", "Get the opening hours of a pickup location."
    )

    def run(self, ctx: ToolContext, args: StoreHoursArgs) -> Any:
        rng = stable_rng(self.name, args)
        opening = rng.choice(["08:00", "09:00"])
        closing = rng.choice(["17:00", "17:30", "18:00"])
        return {"location": args.location, "weekdays": f"{opening}-{closing}", "weekends": "closed"}
