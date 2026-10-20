"""Aggregate clothing trends and feedback without exposing wearer identity.

Queries use bound SQLAlchemy filters. Garment counts are computed in
Python from the stored layer JSON so SQLite tests and PostgreSQL stay
on the same rules.
"""

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Final

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.constants import (
    ANALYTICS_BUCKET_5_TO_10,
    ANALYTICS_BUCKET_11_TO_15,
    ANALYTICS_BUCKET_ABOVE_15,
    ANALYTICS_BUCKET_BELOW_5,
    ANALYTICS_DEFAULT_DAYS,
    ANALYTICS_LAYER_FLEECE,
    ANALYTICS_LAYER_LIGHT_JACKET,
    ANALYTICS_LAYER_T_SHIRT,
    ANALYTICS_LAYER_WINTER_COAT,
    ANALYTICS_MAX_DAYS,
    ANALYTICS_RATING_PERFECT,
    ANALYTICS_RATING_TOO_COLD,
    ANALYTICS_RATING_TOO_WARM,
    ANALYTICS_SENTIMENT_PERFECT,
    ANALYTICS_SENTIMENT_TOO_COLD,
    ANALYTICS_SENTIMENT_TOO_WARM,
    ANALYTICS_TEMP_COLD_BELOW_C,
    ANALYTICS_TEMP_COOL_MAX_C,
    ANALYTICS_TEMP_MILD_MAX_C,
    CARDIGAN,
    FLEECE_MID_LAYER,
    GLOVES,
    INSULATED_MID_LAYER,
    LIGHT_JACKET,
    LIGHT_OVERSHIRT,
    LIGHT_T_SHIRT,
    SCARF,
    SUNGLASSES,
    WARM_HAT,
    WATERPROOF_SHELL,
    WIND_SHELL,
    WINTER_COAT,
    ZIP_HOODIE,
)
from ..models.recommendation import FeedbackEntry, RecommendationLog
from ..models.user import User

_LAYER_SLOTS: Final[tuple[tuple[str, str], ...]] = (
    ("base_layer", "base"),
    ("mid_layer", "mid"),
    ("outer_layer", "outer"),
)
_ACCESSORY_CATEGORY: Final[str] = "accessory"
_CSV_HEADER: Final[tuple[str, ...]] = ("city", "gender", "garment", "category", "count", "percentage")
_GENDER_MALE: Final[str] = "male"
_GENDER_FEMALE: Final[str] = "female"
_GENDER_OTHER: Final[str] = "other"
_GENDER_UNSPECIFIED: Final[str] = "unspecified"
_GENDER_FILTERS: Final[frozenset[str]] = frozenset({_GENDER_MALE, _GENDER_FEMALE, _GENDER_OTHER})
_GENDER_ORDER: Final[tuple[str, ...]] = (
    _GENDER_MALE,
    _GENDER_FEMALE,
    _GENDER_OTHER,
    _GENDER_UNSPECIFIED,
)
_PROFILE_TO_SEGMENT: Final[dict[str, str]] = {
    "men": _GENDER_MALE,
    "male": _GENDER_MALE,
    "women": _GENDER_FEMALE,
    "female": _GENDER_FEMALE,
    "neutral": _GENDER_OTHER,
    "other": _GENDER_OTHER,
}
_SENTIMENT_ORDER: Final[tuple[tuple[str, str], ...]] = (
    (ANALYTICS_RATING_TOO_COLD, ANALYTICS_SENTIMENT_TOO_COLD),
    (ANALYTICS_RATING_PERFECT, ANALYTICS_SENTIMENT_PERFECT),
    (ANALYTICS_RATING_TOO_WARM, ANALYTICS_SENTIMENT_TOO_WARM),
)
_LAYER_GROUPS: Final[tuple[tuple[str, str, frozenset[str]], ...]] = (
    (ANALYTICS_LAYER_WINTER_COAT, "outer", frozenset({WINTER_COAT.id})),
    (
        ANALYTICS_LAYER_LIGHT_JACKET,
        "outer",
        frozenset({LIGHT_JACKET.id, WIND_SHELL.id, WATERPROOF_SHELL.id}),
    ),
    (
        ANALYTICS_LAYER_FLEECE,
        "mid",
        frozenset(
            {
                FLEECE_MID_LAYER.id,
                INSULATED_MID_LAYER.id,
                CARDIGAN.id,
                ZIP_HOODIE.id,
                LIGHT_OVERSHIRT.id,
            }
        ),
    ),
    (ANALYTICS_LAYER_T_SHIRT, "base", frozenset({LIGHT_T_SHIRT.id})),
)
_TRACKED_ACCESSORIES: Final[tuple[str, ...]] = (
    WARM_HAT.id,
    SCARF.id,
    GLOVES.id,
    SUNGLASSES.id,
)


class AnalyticsWindowError(ValueError):
    """Raised when a calendar window is incomplete, reversed, or too long."""


@dataclass(frozen=True)
class TimeWindow:
    """Half-open UTC interval ``[start, end)``. ``start`` may be open."""

    start: datetime | None
    end: datetime

    def day_count(self) -> int:
        """Return the number of UTC dates inside a closed window."""
        if self.start is None:
            raise AnalyticsWindowError("An open window has no day count.")
        return (self.end - self.start).days


@dataclass(frozen=True)
class PurgeResult:
    """Recommendation and feedback rows inside a purge interval."""

    recommendations: int
    feedback: int

    @property
    def total(self) -> int:
        """Return the combined row count."""
        return self.recommendations + self.feedback


@dataclass(frozen=True)
class GarmentStat:
    """One garment's share of the outfits in a slice."""

    garment: str
    category: str
    count: int
    percentage: float


@dataclass(frozen=True)
class TimelinePoint:
    """Recommendations and feedback recorded on one UTC day."""

    day: date
    recommendations: int
    feedback: int


@dataclass(frozen=True)
class SentimentSlice:
    """One thermal-rating share of the feedback in a window."""

    rating: str
    count: int
    percentage: float


@dataclass(frozen=True)
class TemperatureLayerBand:
    """Outer and mid layer groups inside one temperature band."""

    bucket: str
    recommendation_count: int
    layers: list[GarmentStat]


@dataclass(frozen=True)
class GenderShare:
    """Registered accounts in one wearer segment."""

    gender: str
    count: int
    percentage: float


@dataclass(frozen=True)
class KpiSummary:
    """High-level counts for the selected window."""

    total_registered_users: int
    active_wearers: int
    total_recommendations: int
    thermal_satisfaction_rate: float
    most_frequent_garment: str | None
    most_frequent_garment_category: str | None
    most_frequent_garment_count: int
    timeline: list[TimelinePoint]
    sentiment_breakdown: list[SentimentSlice]
    temperature_layer_breakdown: list[TemperatureLayerBand]
    accessories_distribution: list[GarmentStat]
    user_demographics_gender: list[GenderShare]


@dataclass(frozen=True)
class TemperatureBucket:
    """Garments recommended inside one city and temperature band."""

    city: str
    bucket: str
    recommendation_count: int
    garments: list[GarmentStat]


@dataclass(frozen=True)
class ClothingTrend:
    """Garments recommended for one city, temperature band, and gender."""

    city: str
    bucket: str
    gender: str
    recommendation_count: int
    garments: list[GarmentStat]


def segment_from_profile(gender: str | None) -> str:
    """Map a profile gender onto the analytics segment stored with a recommendation."""
    if gender is None:
        return _GENDER_UNSPECIFIED
    return _PROFILE_TO_SEGMENT.get(gender.strip().lower(), _GENDER_UNSPECIFIED)


def normalize_analytics_gender(gender: str | None) -> str | None:
    """Return male, female, or other. Blank and ``all`` mean no filter."""
    if gender is None:
        return None
    text = gender.strip().lower()
    if text in {"", "all"}:
        return None
    if text in _GENDER_FILTERS:
        return text
    raise AnalyticsWindowError("gender must be all, male, female, or other.")


def temperature_bucket(effective_celsius: float) -> str:
    """Return the named band for an effective temperature."""
    if effective_celsius < ANALYTICS_TEMP_COLD_BELOW_C:
        return ANALYTICS_BUCKET_BELOW_5
    if effective_celsius <= ANALYTICS_TEMP_COOL_MAX_C:
        return ANALYTICS_BUCKET_5_TO_10
    if effective_celsius <= ANALYTICS_TEMP_MILD_MAX_C:
        return ANALYTICS_BUCKET_11_TO_15
    return ANALYTICS_BUCKET_ABOVE_15


async def get_kpi_summary(
    db: AsyncSession,
    city: str | None = None,
    days: int = ANALYTICS_DEFAULT_DAYS,
    start_date: date | None = None,
    end_date: date | None = None,
    gender: str | None = None,
) -> KpiSummary:
    """Summarise users, recommendations, satisfaction, and the top garment.

    Registered users are the whole account table. Every other figure uses
    the day window, and the city when one is given. Explicit ``start_date``
    and ``end_date`` replace ``days``. Active wearers are distinct signed-in
    accounts that received a recommendation in that slice. Satisfaction is
    the share of feedback ratings equal to ``PERFECT``. Sentiment, layer
    bands, and accessory shares use that same slice. ``gender`` narrows
    those recommendation figures. Registered users and their gender mix
    stay global.
    """
    window = resolve_query_window(
        days=days,
        start_date=start_date,
        end_date=end_date,
        default_days=ANALYTICS_DEFAULT_DAYS,
    )
    normalized_city = _normalize_city(city)
    segment = normalize_analytics_gender(gender)
    log_filters = _log_filters(window, normalized_city)
    registered = await db.scalar(select(func.count()).select_from(User))
    recommendations = await db.scalar(
        _scoped_logs(select(func.count()).select_from(RecommendationLog), segment).where(*log_filters)
    )
    active = await db.scalar(
        _scoped_logs(
            select(func.count(func.distinct(RecommendationLog.user_id))),
            segment,
        ).where(*log_filters, RecommendationLog.user_id.is_not(None))
    )
    ratings = await _feedback_ratings(db, window, normalized_city, segment)
    perfect = sum(1 for rating in ratings if rating == ANALYTICS_RATING_PERFECT)
    outfits = await _outfit_rows(db, window, normalized_city, segment)
    layers = [layers for _effective, layers in outfits]
    top_garment, top_category, top_count = _most_frequent(layers)
    timeline = await get_timeline_volume(db, city=normalized_city, window=window, gender=segment)
    return KpiSummary(
        total_registered_users=int(registered or 0),
        active_wearers=int(active or 0),
        total_recommendations=int(recommendations or 0),
        thermal_satisfaction_rate=_percentage(perfect, len(ratings)),
        most_frequent_garment=top_garment,
        most_frequent_garment_category=top_category,
        most_frequent_garment_count=top_count,
        timeline=timeline,
        sentiment_breakdown=_sentiment_breakdown(ratings),
        temperature_layer_breakdown=_temperature_layer_breakdown(outfits),
        accessories_distribution=_accessories_distribution(layers),
        user_demographics_gender=await _user_demographics(db),
    )


async def get_garment_distribution_by_city(
    db: AsyncSession,
    city: str,
    days: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[GarmentStat]:
    """Count each garment in one city and its share of all pieces shown."""
    window = resolve_query_window(
        days=days,
        start_date=start_date,
        end_date=end_date,
        default_days=days,
    )
    normalized_city = _normalize_city(city)
    if normalized_city is None:
        return []
    layers = await _layer_rows(db, window, normalized_city)
    return _distribution(layers)


async def get_temperature_threshold_correlations(
    db: AsyncSession,
    city: str | None = None,
    days: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[TemperatureBucket]:
    """Group recommended pieces by recorded city and temperature band.

    With no dates and no ``days``, every stored log is included. A window
    narrows the logs when the caller supplies one. ``city`` keeps one place
    when it is provided. Each row keeps the city name stored on the log.
    """
    normalized_city = _normalize_city(city)
    statement = select(
        RecommendationLog.location_name,
        RecommendationLog.effective_temperature,
        RecommendationLog.recommended_layers,
    )
    if start_date is not None or end_date is not None or days is not None:
        window = resolve_query_window(
            days=days,
            start_date=start_date,
            end_date=end_date,
            default_days=ANALYTICS_DEFAULT_DAYS,
        )
        statement = statement.where(*_time_filters(RecommendationLog.created_at, window))
    if normalized_city is not None:
        statement = statement.where(func.lower(RecommendationLog.location_name) == normalized_city)
    rows = (await db.execute(statement)).all()
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    counts: Counter[tuple[str, str]] = Counter()
    for location_name, effective, layers in rows:
        key = (str(location_name), temperature_bucket(float(effective)))
        counts[key] += 1
        grouped[key].append(_as_mapping(layers))
    cities = sorted({name for name, _label in counts})
    return [
        TemperatureBucket(
            city=city_name,
            bucket=label,
            recommendation_count=counts[(city_name, label)],
            garments=_distribution(grouped[(city_name, label)]),
        )
        for city_name in cities
        for label in _bucket_labels()
        if counts[(city_name, label)] > 0
    ]


async def get_clothing_trends(
    db: AsyncSession,
    city: str | None = None,
    days: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    gender: str | None = None,
) -> list[ClothingTrend]:
    """Group recommended pieces by city, temperature band, and wearer gender.

    ``gender`` keeps one segment. Blank and ``all`` keep every segment,
    including unspecified guests. A stored segment wins. An empty historical
    value falls back to the wearer's profile gender.
    """
    segment = normalize_analytics_gender(gender)
    normalized_city = _normalize_city(city)
    statement = select(
        RecommendationLog.location_name,
        RecommendationLog.effective_temperature,
        RecommendationLog.recommended_layers,
        wearer_gender_expr().label("wearer_gender"),
    ).outerjoin(User, RecommendationLog.user_id == User.id)
    if start_date is not None or end_date is not None or days is not None:
        window = resolve_query_window(
            days=days,
            start_date=start_date,
            end_date=end_date,
            default_days=ANALYTICS_DEFAULT_DAYS,
        )
        statement = statement.where(*_time_filters(RecommendationLog.created_at, window))
    if normalized_city is not None:
        statement = statement.where(func.lower(RecommendationLog.location_name) == normalized_city)
    if segment is not None:
        statement = statement.where(wearer_gender_expr() == segment)
    rows = (await db.execute(statement)).all()
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    counts: Counter[tuple[str, str, str]] = Counter()
    for location_name, effective, layers, wearer_gender in rows:
        key = (str(location_name), temperature_bucket(float(effective)), str(wearer_gender))
        counts[key] += 1
        grouped[key].append(_as_mapping(layers))
    cities = sorted({name for name, _label, _gender in counts})
    return [
        ClothingTrend(
            city=city_name,
            bucket=label,
            gender=wearer_gender,
            recommendation_count=counts[(city_name, label, wearer_gender)],
            garments=_distribution(grouped[(city_name, label, wearer_gender)]),
        )
        for city_name in cities
        for label in _bucket_labels()
        for wearer_gender in _GENDER_ORDER
        if counts[(city_name, label, wearer_gender)] > 0
    ]


async def get_timeline_volume(
    db: AsyncSession,
    days: int = ANALYTICS_DEFAULT_DAYS,
    city: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    window: TimeWindow | None = None,
    gender: str | None = None,
) -> list[TimelinePoint]:
    """Return one point per UTC day, including days with no activity."""
    bounds = window or resolve_query_window(
        days=days,
        start_date=start_date,
        end_date=end_date,
        default_days=ANALYTICS_DEFAULT_DAYS,
    )
    if bounds.start is None:
        raise AnalyticsWindowError("A timeline needs a start date.")
    start_day = bounds.start.date()
    normalized_city = _normalize_city(city)
    segment = normalize_analytics_gender(gender)
    log_filters = _log_filters(bounds, normalized_city)
    log_rows = await db.execute(
        _scoped_logs(select(RecommendationLog.created_at), segment).where(*log_filters)
    )
    feedback_statement = _scoped_logs(
        select(FeedbackEntry.created_at).join(
            RecommendationLog,
            FeedbackEntry.recommendation_id == RecommendationLog.id,
        ),
        segment,
    ).where(*_time_filters(FeedbackEntry.created_at, bounds))
    if normalized_city is not None:
        feedback_statement = feedback_statement.where(
            func.lower(RecommendationLog.location_name) == normalized_city
        )
    feedback_rows = await db.execute(feedback_statement)
    recommendations: Counter[date] = Counter(_utc_day(value) for (value,) in log_rows.all())
    feedback: Counter[date] = Counter(_utc_day(value) for (value,) in feedback_rows.all())
    points: list[TimelinePoint] = []
    for offset in range(bounds.day_count()):
        day = start_day + timedelta(days=offset)
        points.append(
            TimelinePoint(
                day=day,
                recommendations=recommendations[day],
                feedback=feedback[day],
            )
        )
    return points


async def build_clothing_trends_csv(
    db: AsyncSession,
    city: str | None = None,
    days: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
    window: TimeWindow | None = None,
    gender: str | None = None,
) -> str:
    """Build an anonymized CSV of garment counts. No wearer fields are included.

    An explicit ``window`` is used for maintenance archives and may be open
    at the start. Public queries resolve ``days`` or a closed date pair and
    stay inside the analytics day cap.
    """
    bounds = window or resolve_query_window(
        days=days,
        start_date=start_date,
        end_date=end_date,
        default_days=days,
    )
    normalized_city = _normalize_city(city)
    segment = normalize_analytics_gender(gender)
    statement = (
        select(
            RecommendationLog.location_name,
            RecommendationLog.recommended_layers,
            wearer_gender_expr().label("wearer_gender"),
        )
        .outerjoin(User, RecommendationLog.user_id == User.id)
        .where(*_log_filters(bounds, normalized_city))
    )
    if segment is not None:
        statement = statement.where(wearer_gender_expr() == segment)
    rows = (await db.execute(statement)).all()
    by_slice: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for location_name, layers, wearer_gender in rows:
        by_slice[(str(location_name), str(wearer_gender))].append(_as_mapping(layers))
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_CSV_HEADER)
    for location_name, wearer_gender in sorted(by_slice):
        for stat in _distribution(by_slice[(location_name, wearer_gender)]):
            writer.writerow(
                [
                    location_name,
                    wearer_gender,
                    stat.garment,
                    stat.category,
                    stat.count,
                    f"{stat.percentage:.1f}",
                ]
            )
    return buffer.getvalue()


def _bucket_labels() -> tuple[str, ...]:
    """Return temperature bands from coldest to warmest."""
    return (
        ANALYTICS_BUCKET_BELOW_5,
        ANALYTICS_BUCKET_5_TO_10,
        ANALYTICS_BUCKET_11_TO_15,
        ANALYTICS_BUCKET_ABOVE_15,
    )


def resolve_query_window(
    *,
    days: int | None,
    start_date: date | None,
    end_date: date | None,
    default_days: int,
) -> TimeWindow:
    """Return the UTC window for an analytics query.

    A complete start and end pair replaces ``days``. The pair is inclusive
    on both calendar dates and cannot be longer than the analytics cap.
    """
    if start_date is not None or end_date is not None:
        if start_date is None or end_date is None:
            raise AnalyticsWindowError("start_date and end_date must both be provided.")
        if end_date < start_date:
            raise AnalyticsWindowError("end_date must be on or after start_date.")
        span = (end_date - start_date).days + 1
        if span > ANALYTICS_MAX_DAYS:
            raise AnalyticsWindowError(
                f"The date range must be {ANALYTICS_MAX_DAYS} days or shorter."
            )
        return TimeWindow(start=_midnight(start_date), end=_midnight(end_date + timedelta(days=1)))
    bounded = _bounded_days(default_days if days is None else days)
    today = datetime.now(timezone.utc).date()
    return TimeWindow(
        start=_midnight(today - timedelta(days=bounded - 1)),
        end=_midnight(today + timedelta(days=1)),
    )


def resolve_purge_window(
    *,
    before_date: date | None,
    start_date: date | None,
    end_date: date | None,
) -> TimeWindow:
    """Return the interval whose recommendation history may be removed.

    ``before_date`` deletes everything strictly older than that UTC date.
    A start and end pair deletes that inclusive calendar span. The two
    forms cannot be combined, and an empty request is rejected so a purge
    cannot cover the whole table by accident.
    """
    has_before = before_date is not None
    has_range = start_date is not None or end_date is not None
    if has_before and has_range:
        raise AnalyticsWindowError("Provide only one interval: before_date, or a start and end date.")
    if has_before and before_date is not None:
        return TimeWindow(start=None, end=_midnight(before_date))
    if start_date is None or end_date is None:
        raise AnalyticsWindowError("Provide before_date, or both start_date and end_date.")
    if end_date < start_date:
        raise AnalyticsWindowError("end_date must be on or after start_date.")
    return TimeWindow(start=_midnight(start_date), end=_midnight(end_date + timedelta(days=1)))


async def count_historical_logs(db: AsyncSession, window: TimeWindow) -> PurgeResult:
    """Count recommendation and feedback rows a purge would remove."""
    recommendations = await db.scalar(
        select(func.count()).select_from(RecommendationLog).where(*_log_filters(window, None))
    )
    feedback = await db.scalar(
        select(func.count()).select_from(FeedbackEntry).where(_feedback_purge_filter(window))
    )
    return PurgeResult(recommendations=int(recommendations or 0), feedback=int(feedback or 0))


async def purge_historical_logs(
    db: AsyncSession,
    window: TimeWindow,
    *,
    export_first: bool,
) -> PurgeResult:
    """Delete recommendation history in ``window`` and return the row counts.

    When ``export_first`` is set, the anonymized garment CSV is built before
    any delete. A failure there leaves the tables unchanged.
    """
    if export_first:
        await build_clothing_trends_csv(db, window=window)
    measured = await count_historical_logs(db, window)
    await db.execute(delete(FeedbackEntry).where(_feedback_purge_filter(window)))
    await db.execute(delete(RecommendationLog).where(*_log_filters(window, None)))
    return measured


def _feedback_purge_filter(window: TimeWindow) -> object:
    """Match feedback written in the interval or attached to a purged log."""
    log_ids = select(RecommendationLog.id).where(*_log_filters(window, None))
    return or_(
        and_(*_time_filters(FeedbackEntry.created_at, window)),
        FeedbackEntry.recommendation_id.in_(log_ids),
    )


def _midnight(day: date) -> datetime:
    """Return midnight UTC on ``day``."""
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)


def _bounded_days(days: int) -> int:
    """Clamp a window to the supported analytics range."""
    return min(max(int(days), 1), ANALYTICS_MAX_DAYS)


def _normalize_city(city: str | None) -> str | None:
    """Return a lowercase city key, or None when the filter is blank."""
    if city is None:
        return None
    text = city.strip().lower()
    if text == "":
        return None
    return text


def _time_filters(column: object, window: TimeWindow) -> list[object]:
    """Bound a timestamp column by the half-open window."""
    filters: list[object] = []
    if window.start is not None:
        filters.append(column >= window.start)
    filters.append(column < window.end)
    return filters


def _log_filters(window: TimeWindow, normalized_city: str | None) -> list[object]:
    """Bound recommendation rows by time and, when set, location name."""
    filters = _time_filters(RecommendationLog.created_at, window)
    if normalized_city is not None:
        filters.append(func.lower(RecommendationLog.location_name) == normalized_city)
    return filters


def wearer_gender_expr() -> object:
    """Resolve the wearer segment, using the profile when the log has none.

    A stored male, female, or other value wins. ``unspecified`` and blank
    historical rows fall back to ``users.gender``.
    """
    stored = func.lower(func.coalesce(RecommendationLog.gender, ""))
    profile = func.lower(func.coalesce(User.gender, ""))
    return case(
        (stored.in_((_GENDER_MALE, _GENDER_FEMALE, _GENDER_OTHER)), stored),
        (profile.in_(("men", "male")), _GENDER_MALE),
        (profile.in_(("women", "female")), _GENDER_FEMALE),
        (profile.in_(("neutral", "other")), _GENDER_OTHER),
        else_=_GENDER_UNSPECIFIED,
    )


def _scoped_logs(statement: object, segment: str | None) -> object:
    """Left-join the wearer and keep one gender segment when one is selected."""
    if segment is None:
        return statement
    return statement.outerjoin(User, RecommendationLog.user_id == User.id).where(
        wearer_gender_expr() == segment
    )


async def _user_demographics(db: AsyncSession) -> list[GenderShare]:
    """Count registered accounts as male, female, and other."""
    rows = (await db.execute(select(User.gender, func.count()).group_by(User.gender))).all()
    counts = {_GENDER_MALE: 0, _GENDER_FEMALE: 0, _GENDER_OTHER: 0}
    for raw, count in rows:
        segment = segment_from_profile(str(raw) if raw is not None else None)
        if segment not in counts:
            segment = _GENDER_OTHER
        counts[segment] += int(count)
    total = sum(counts.values())
    return [
        GenderShare(gender=key, count=counts[key], percentage=_percentage(counts[key], total))
        for key in (_GENDER_MALE, _GENDER_FEMALE, _GENDER_OTHER)
    ]


async def _feedback_ratings(
    db: AsyncSession,
    window: TimeWindow,
    normalized_city: str | None,
    segment: str | None = None,
) -> list[str]:
    """Return thermal ratings whose feedback falls inside the slice."""
    statement = _scoped_logs(
        select(FeedbackEntry.thermal_rating).join(
            RecommendationLog,
            FeedbackEntry.recommendation_id == RecommendationLog.id,
        ),
        segment,
    ).where(*_time_filters(FeedbackEntry.created_at, window))
    if normalized_city is not None:
        statement = statement.where(func.lower(RecommendationLog.location_name) == normalized_city)
    rows = await db.execute(statement)
    return [str(rating) for (rating,) in rows.all()]


async def _outfit_rows(
    db: AsyncSession,
    window: TimeWindow,
    normalized_city: str | None,
    segment: str | None = None,
) -> list[tuple[float, dict[str, object]]]:
    """Load effective temperature and outfit JSON for logs inside the slice."""
    rows = await db.execute(
        _scoped_logs(
            select(
                RecommendationLog.effective_temperature,
                RecommendationLog.recommended_layers,
            ),
            segment,
        ).where(*_log_filters(window, normalized_city))
    )
    return [(float(effective), _as_mapping(layers)) for effective, layers in rows.all()]


async def _layer_rows(
    db: AsyncSession,
    window: TimeWindow,
    normalized_city: str | None,
) -> list[dict[str, object]]:
    """Load outfit JSON for logs inside the slice."""
    rows = await db.execute(
        select(RecommendationLog.recommended_layers).where(*_log_filters(window, normalized_city))
    )
    return [_as_mapping(layers) for (layers,) in rows.all()]


def _as_mapping(value: object) -> dict[str, object]:
    """Keep a decoded JSON object and ignore any other stored shape."""
    if isinstance(value, dict):
        return value
    return {}


def _garments_in(layers: dict[str, object]) -> list[tuple[str, str]]:
    """Yield garment id and category for each piece in one outfit."""
    found: list[tuple[str, str]] = []
    for slot, category in _LAYER_SLOTS:
        piece = layers.get(slot)
        parsed = _garment_id(piece)
        if parsed is not None:
            found.append((parsed, category))
    accessories = layers.get("accessories")
    if isinstance(accessories, list):
        for piece in accessories:
            parsed = _garment_id(piece)
            if parsed is not None:
                found.append((parsed, _ACCESSORY_CATEGORY))
    return found


def _garment_id(piece: object) -> str | None:
    """Return a garment id when the stored piece has one."""
    if not isinstance(piece, dict):
        return None
    raw = piece.get("id")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text == "":
        return None
    return text


def _distribution(layers_rows: list[dict[str, object]]) -> list[GarmentStat]:
    """Count pieces and convert each count to a percentage of the total."""
    counts: Counter[tuple[str, str]] = Counter()
    for layers in layers_rows:
        counts.update(_garments_in(layers))
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    return [
        GarmentStat(
            garment=garment,
            category=category,
            count=count,
            percentage=_percentage(count, total),
        )
        for (garment, category), count in ranked
    ]


def _sentiment_breakdown(ratings: list[str]) -> list[SentimentSlice]:
    """Count too-cold, perfect, and too-warm ratings in a stable order."""
    counts: Counter[str] = Counter(rating.strip().upper() for rating in ratings)
    recognized = sum(counts[stored] for stored, _public in _SENTIMENT_ORDER)
    return [
        SentimentSlice(
            rating=public,
            count=counts[stored],
            percentage=_percentage(counts[stored], recognized),
        )
        for stored, public in _SENTIMENT_ORDER
    ]


def _temperature_layer_breakdown(
    outfits: list[tuple[float, dict[str, object]]],
) -> list[TemperatureLayerBand]:
    """Count winter coats, light jackets, fleece, and T-shirts in each band.

    A light jacket includes the wind shell and the waterproof shell. Fleece
    includes knit mid layers a wearer can put over a shirt. Percentages are
    the share of outfits in that band which include the group, so an outfit
    with both a fleece and a jacket is counted in both.
    """
    grouped: dict[str, list[dict[str, object]]] = {label: [] for label in _bucket_labels()}
    for effective, layers in outfits:
        grouped[temperature_bucket(effective)].append(layers)
    bands: list[TemperatureLayerBand] = []
    for label in _bucket_labels():
        rows = grouped[label]
        layers: list[GarmentStat] = []
        for garment, category, members in _LAYER_GROUPS:
            count = sum(1 for outfit in rows if _outfit_ids(outfit) & members)
            layers.append(
                GarmentStat(
                    garment=garment,
                    category=category,
                    count=count,
                    percentage=_percentage(count, len(rows)),
                )
            )
        bands.append(
            TemperatureLayerBand(
                bucket=label,
                recommendation_count=len(rows),
                layers=layers,
            )
        )
    return bands


def _accessories_distribution(layers_rows: list[dict[str, object]]) -> list[GarmentStat]:
    """Count the tracked accessories and their share of that set."""
    counts: Counter[str] = Counter()
    for layers in layers_rows:
        present = _outfit_ids(layers)
        for accessory in _TRACKED_ACCESSORIES:
            if accessory in present:
                counts[accessory] += 1
    total = sum(counts.values())
    return [
        GarmentStat(
            garment=accessory,
            category=_ACCESSORY_CATEGORY,
            count=counts[accessory],
            percentage=_percentage(counts[accessory], total),
        )
        for accessory in _TRACKED_ACCESSORIES
    ]


def _outfit_ids(layers: dict[str, object]) -> set[str]:
    """Return every garment id worn in one stored outfit."""
    return {garment for garment, _category in _garments_in(layers)}


def _most_frequent(layers_rows: list[dict[str, object]]) -> tuple[str | None, str | None, int]:
    """Return the garment id, category, and count that appears most often."""
    stats = _distribution(layers_rows)
    if not stats:
        return None, None, 0
    top = stats[0]
    return top.garment, top.category, top.count


def _percentage(count: int, total: int) -> float:
    """Return a one-decimal percentage, or 0 when the total is empty."""
    if total <= 0:
        return 0.0
    return round(count * 100.0 / total, 1)


def _utc_day(value: datetime) -> date:
    """Return the UTC calendar day for a stored timestamp."""
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(timezone.utc).date()
