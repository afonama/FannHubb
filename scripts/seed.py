"""Seed Fan Hub Plus with a realistic demo dataset.

Idempotent: re-running skips rows that already exist (matched on natural keys),
so it is safe to point at a database that has already been seeded.

    python scripts/seed.py

Credentials are printed at the end (and come from .env via app.core.config).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import random
import sys
from pathlib import Path
from typing import Any, Optional

# Allow `python scripts/seed.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging_config import configure_logging, get_logger  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.models import (  # noqa: E402
    Category,
    Character,
    ChatbotFaq,
    Content,
    ContentStatus,
    ContentType,
    Event,
    FanSubmission,
    Feedback,
    FeedbackStatus,
    FeedbackType,
    Merchandise,
    Rating,
    RatingScale,
    SubmissionStatus,
    Tag,
    User,
    UserPreference,
    UserRole,
)
from app.db.session import async_session_maker, dispose_engine  # noqa: E402
from app.services import popularity_service  # noqa: E402

logger = get_logger("seed")
random.seed(1337)

TODAY = dt.date.today()


# --------------------------------------------------------------- reference
CATEGORIES: list[dict[str, Any]] = [
    {
        "name": "Anime",
        "slug": "anime",
        "description": "Series, films and news from Japanese animation studios.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/anime.svg",
    },
    {
        "name": "Gaming",
        "slug": "gaming",
        "description": "Game releases, esports, reviews and patch notes.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/gaming.svg",
    },
    {
        "name": "Movies",
        "slug": "movies",
        "description": "Blockbusters, indie films, trailers and reviews.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/movies.svg",
    },
    {
        "name": "TV Shows",
        "slug": "tv-shows",
        "description": "Series seasons, episode guides and fan theories.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/tv.svg",
    },
    {
        "name": "K-Pop",
        "slug": "k-pop",
        "description": "Groups, comebacks, albums and concert tours.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/kpop.svg",
    },
    {
        "name": "Comics",
        "slug": "comics",
        "description": "Superhero books, graphic novels and creator spotlights.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/comics.svg",
    },
    {
        "name": "Manga",
        "slug": "manga",
        "description": "Manga series, chapter talk and publishing news.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/manga.svg",
    },
    {
        "name": "Cosplay",
        "slug": "cosplay",
        "description": "Cosplay builds, convention reports and tutorials.",
        "icon_url": "https://cdn.fanhubplus.dev/icons/cosplay.svg",
    },
]

#: 5 content items per category, tagged with genres/years/types.
CONTENT_SEED: dict[str, list[dict[str, Any]]] = {
    "anime": [
        {
            "title": "Blue Lock: the striker who wanted to be a genius",
            "type": ContentType.ARTICLE,
            "description": "A ruthless football academy turns ego into a weapon in this dark sports anime.",
            "body": "Blue Lock reimagines the striker as a predator...",
            "tags": ["sports", "shounen", "football"],
            "year": 2023,
            "views": 18400,
        },
        {
            "title": "Frieren: beyond questing, remembering",
            "type": ContentType.ARTICLE,
            "description": "An elf mage retraces a century-long journey after her party is gone.",
            "body": "Frieren is a quiet masterclass in grief and time...",
            "tags": ["fantasy", "seinen", "drama"],
            "year": 2023,
            "views": 42300,
        },
        {
            "title": "Jujutsu Kaisen season 2 opening breakdown",
            "type": ContentType.VIDEO,
            "description": "Frame-by-frame analysis of the Shibuya incident opening.",
            "body": "Every cut lands on the beat...",
            "media_url": "https://cdn.fanhubplus.dev/video/jjk-s2-op.mp4",
            "tags": ["action", "shounen", "analysis"],
            "year": 2024,
            "views": 27100,
        },
        {
            "title": "Vinland Saga episode 24 - the quietest revenge",
            "type": ContentType.ARTICLE,
            "description": "Thorfinn's arc closes on a farm, a grudge and a moment of grace.",
            "body": "Revenge is the least interesting part...",
            "tags": ["historical", "seinen", "revenge"],
            "year": 2022,
            "views": 15900,
        },
        {
            "title": "Cosplay spotlight: the Kaneda armour build",
            "type": ContentType.IMAGE,
            "description": "A 14-month build of Kaneda's iconic motorcycle armour, photographed at three angles.",
            "media_url": "https://cdn.fanhubplus.dev/img/kaneda-armour.jpg",
            "tags": ["build-log", "cosplay", "props"],
            "year": 2024,
            "views": 8600,
        },
    ],
    "gaming": [
        {
            "title": "Elden Ring: why the demigod remix changed the meta",
            "type": ContentType.ARTICLE,
            "description": "Rewarding patience instead of time, and how that reshaped the meta.",
            "body": "The remix traded punishment for mastery...",
            "tags": ["action-rpg", "open-world", "meta"],
            "year": 2023,
            "views": 51200,
        },
        {
            "title": "Palworld vs the survival genre",
            "type": ContentType.ARTICLE,
            "description": "A look at how creature collectors borrowed from survival games.",
            "body": "Palworld is less a survival game than a loot treadmill...",
            "tags": ["survival", "multiplayer", "mmo"],
            "year": 2024,
            "views": 33800,
        },
        {
            "title": "Speedrun tech: frame-perfect inputs in Sekiro",
            "type": ContentType.VIDEO,
            "description": "How deflect timing works at 60fps and why one frame matters.",
            "media_url": "https://cdn.fanhubplus.dev/video/sekiro-tech.mp4",
            "tags": ["speedrun", "fighting", "tech"],
            "year": 2022,
            "views": 9800,
        },
        {
            "title": "Indie gems of the year so far",
            "type": ContentType.ARTICLE,
            "description": "Ten small-team games that out-pedestal the AAA calendar.",
            "body": "Small teams, enormous ideas...",
            "tags": ["indie", "recommendation", "rpg"],
            "year": 2024,
            "views": 14600,
        },
        {
            "title": "Esports desk: the grand final that went to five maps",
            "type": ContentType.AUDIO,
            "description": "Full caster audio of the deciding map of the season finals.",
            "media_url": "https://cdn.fanhubplus.dev/audio/finals-map5.mp3",
            "tags": ["esports", "tournament", "commentary"],
            "year": 2024,
            "views": 7300,
        },
    ],
    "movies": [
        {
            "title": "The wildest sci-fi of the decade, ranked",
            "type": ContentType.ARTICLE,
            "description": "From derelict ships to collapsing timelines - the best space cinema of the 2020s.",
            "body": "Science fiction keeps asking the same question...",
            "tags": ["sci-fi", "ranking", "space"],
            "year": 2024,
            "views": 22300,
        },
        {
            "title": "A24's quiet comeback with Past Lives",
            "type": ContentType.ARTICLE,
            "description": "A film about the life you nearly lived, told in three conversations.",
            "body": "Nora never says what she almost said...",
            "tags": ["drama", "romance", "a24"],
            "year": 2023,
            "views": 28900,
        },
        {
            "title": "Trailer watch: the best animated trailers of 2024",
            "type": ContentType.VIDEO,
            "description": "Six trailers, one playlist, zero sequels required.",
            "media_url": "https://cdn.fanhubplus.dev/video/trailers-2024.mp4",
            "tags": ["animation", "trailer", "family"],
            "year": 2024,
            "views": 11200,
        },
        {
            "title": "Why studios keep greenlighting remakes",
            "type": ContentType.ARTICLE,
            "description": "The economics behind nostalgia, and what it costs audiences.",
            "body": "Nostalgia is a reliable business model...",
            "tags": ["industry", "business", "analysis"],
            "year": 2022,
            "views": 6400,
        },
        {
            "title": "Stills gallery: the cinematography of rain",
            "type": ContentType.IMAGE,
            "description": "Production stills that prove lighting carries the mood in every scene.",
            "media_url": "https://cdn.fanhubplus.dev/img/rain-stills.jpg",
            "tags": ["cinematography", "art", "gallery"],
            "year": 2024,
            "views": 5100,
        },
    ],
    "tv-shows": [
        {
            "title": "Severance: the hallway scenes decoded",
            "type": ContentType.ARTICLE,
            "description": "Every corridor in Lumon is a puzzle. Here is how to read them.",
            "body": "The maze is not a metaphor, it is a floor plan...",
            "tags": ["thriller", "mystery", "sci-fi"],
            "year": 2022,
            "views": 36700,
        },
        {
            "title": "The Bear is a stress test for television",
            "type": ContentType.ARTICLE,
            "description": "Twenty-minute episodes, three timelines and one kitchen that will end you.",
            "body": "It is chaos, but it is choreographed chaos...",
            "tags": ["drama", "comedy", "ensemble"],
            "year": 2023,
            "views": 19900,
        },
        {
            "title": "Ranking every anime adaptation live",
            "type": ContentType.VIDEO,
            "description": "A community stream debating Sailor Moon vs. Berserk.",
            "media_url": "https://cdn.fanhubplus.dev/video/adaptations-live.mp4",
            "tags": ["anime", "ranking", "live"],
            "year": 2024,
            "views": 8900,
        },
        {
            "title": "The best sitcoms that ended on a downbeat note",
            "type": ContentType.ARTICLE,
            "description": "Nine shows that refused a laugh track in the finale.",
            "body": "A happy ending is not always the kind one...",
            "tags": ["sitcom", "comedy", "ending"],
            "year": 2021,
            "views": 7200,
        },
        {
            "title": "Score listening: three minutes of pure dread",
            "type": ContentType.AUDIO,
            "description": "A curated playlist of horror-tingled score highlights from streaming shows.",
            "media_url": "https://cdn.fanhubplus.dev/audio/dread-score.mp3",
            "tags": ["soundtrack", "horror", "playlist"],
            "year": 2024,
            "views": 4300,
        },
    ],
    "k-pop": [
        {
            "title": "Album review: midnight synths and honest lyrics",
            "type": ContentType.ARTICLE,
            "description": "A comeback album that refuses to stay in one mood.",
            "body": "The title track is patient where you expect instant payoff...",
            "tags": ["review", "comeback", "synth-pop"],
            "year": 2024,
            "views": 31400,
        },
        {
            "title": "Concert recap: three songs that stopped the arena",
            "type": ContentType.ARTICLE,
            "description": "Setlist highlights, crowd reactions and the encore nobody expected.",
            "body": "The encore stripped the arrangement back to a piano...",
            "tags": ["concert", "live", "recap"],
            "year": 2024,
            "views": 27600,
        },
        {
            "title": "MV choreography breakdown: the mirror sequence",
            "type": ContentType.VIDEO,
            "description": "Eight dancers, four cameras, one mirrored formation repeated for a full chorus.",
            "media_url": "https://cdn.fanhubplus.dev/video/mv-mirror.mp4",
            "tags": ["choreography", "music-video", "performance"],
            "year": 2023,
            "views": 45200,
        },
        {
            "title": "A fan's guide to touring in Seoul",
            "type": ContentType.ARTICLE,
            "description": "Getting tickets, transport and etiquette for first-time concertgoers.",
            "body": "Prepare for a queue, not a gamble...",
            "tags": ["guide", "concert", "seoul"],
            "year": 2023,
            "views": 16800,
        },
        {
            "title": "Vocal masterclass: belts that actually land",
            "type": ContentType.AUDIO,
            "description": "Six vocal takes with the production stripped back.",
            "media_url": "https://cdn.fanhubplus.dev/audio/vocal-masterclass.mp3",
            "tags": ["vocals", "production", "technique"],
            "year": 2024,
            "views": 6900,
        },
    ],
    "comics": [
        {
            "title": "The slow burn finally pays off in issue #60",
            "type": ContentType.ARTICLE,
            "description": "Nine years of setup collapses into a single double-page spread.",
            "body": "The payoff earns its size because the buildup never rushed...",
            "tags": ["superhero", "review", "comic-book"],
            "year": 2024,
            "views": 14300,
        },
        {
            "title": "Why graphic novels are perfect for adaptation",
            "type": ContentType.ARTICLE,
            "description": "Page turns, panel rhythm and limited series - a match made for TV.",
            "body": "A comic is already storyboarded...",
            "tags": ["adaptation", "analysis", "indie"],
            "year": 2023,
            "views": 9700,
        },
        {
            "title": "Cover art gallery: the year's best variants",
            "type": ContentType.IMAGE,
            "description": "Twenty variant covers, from minimalist to completely deranged.",
            "media_url": "https://cdn.fanhubplus.dev/img/variant-covers.jpg",
            "tags": ["gallery", "art", "collectible"],
            "year": 2024,
            "views": 8100,
        },
        {
            "title": "The indie press is having a renaissance",
            "type": ContentType.ARTICLE,
            "description": "Small publishers are printing the most exciting books of the decade.",
            "body": "Print is not dying, it is fragmenting...",
            "tags": ["indie", "publishing", "business"],
            "year": 2022,
            "views": 5200,
        },
        {
            "title": "Panel-by-panel: the best splash page of the year",
            "type": ContentType.ARTICLE,
            "description": "One image, three hundred words of story, and no dialogue at all.",
            "body": "Silent panels can carry more than a paragraph...",
            "tags": ["art", "technique", "analysis"],
            "year": 2024,
            "views": 6100,
        },
    ],
    "manga": [
        {
            "title": "Chapter 200 and still escalating: a manga milestone",
            "type": ContentType.ARTICLE,
            "description": "Two hundred chapters later the tournament arc finally pays off.",
            "body": "Momentum is a manga's best asset...",
            "tags": ["sports", "shonen", "milestone"],
            "year": 2024,
            "views": 12900,
        },
        {
            "title": "Seinen but make it comforting",
            "type": ContentType.ARTICLE,
            "description": "Grown-up stories that still leave you feeling held.",
            "body": "Bleakness with an ending in sight...",
            "tags": ["seinen", "slice-of-life", "recommendation"],
            "year": 2023,
            "views": 11600,
        },
        {
            "title": "The summer anime that was adapted from a 1997 manga",
            "type": ContentType.ARTICLE,
            "description": "An old series gets a new adaptation and finds a new audience.",
            "body": "Some stories only land at the right age...",
            "tags": ["adaptation", "classic", "shounen"],
            "year": 2024,
            "views": 7400,
        },
        {
            "title": "Panel art timelapse: inking a full chapter",
            "type": ContentType.VIDEO,
            "description": "Twelve hours compressed into eight minutes of screentone and brush.",
            "media_url": "https://cdn.fanhubplus.dev/video/inking-timelapse.mp4",
            "tags": ["tutorial", "art", "behind-the-scenes"],
            "year": 2023,
            "views": 19300,
        },
        {
            "title": "Manga panel grid reference pack",
            "type": ContentType.IMAGE,
            "description": "A printable sheet of the twelve most useful panel layouts.",
            "media_url": "https://cdn.fanhubplus.dev/img/panel-grids.jpg",
            "tags": ["tutorial", "art", "reference"],
            "year": 2024,
            "views": 13800,
        },
    ],
    "cosplay": [
        {
            "title": "Wig styling: three curls that hold all day",
            "type": ContentType.ARTICLE,
            "description": "Heat, setting spray and patience are the whole recipe.",
            "body": "Curl sets fail when people rush the cooling phase...",
            "tags": ["wig", "tutorial", "hair"],
            "year": 2023,
            "views": 15600,
        },
        {
            "title": "Foam armour from scratch",
            "type": ContentType.ARTICLE,
            "description": "Cutting, sealing and painting EVA foam into something that looks like metal.",
            "body": "Worbla and foam solve different problems...",
            "tags": ["armour", "tutorial", "props"],
            "year": 2024,
            "views": 12100,
        },
        {
            "title": "Convention floor report: the cosplay that stopped everyone",
            "type": ContentType.ARTICLE,
            "description": "Our photographer's pick of the single best build on the floor.",
            "body": "The detail that sold it was a hand-painted seam...",
            "tags": ["convention", "report", "inspiration"],
            "year": 2024,
            "views": 9800,
        },
        {
            "title": "Repairing a snapped EVA edge",
            "type": ContentType.VIDEO,
            "description": "A 6-minute repair you can do the night before a convention.",
            "media_url": "https://cdn.fanhubplus.dev/video/eva-repair.mp4",
            "tags": ["repair", "tutorial", "eva"],
            "year": 2022,
            "views": 6700,
        },
        {
            "title": "Group shoot gallery: our top ten builds",
            "type": ContentType.IMAGE,
            "description": "Ten characters, one photographer, and a lot of good light.",
            "media_url": "https://cdn.fanhubplus.dev/img/group-shoot.jpg",
            "tags": ["gallery", "photoshoot", "inspiration"],
            "year": 2024,
            "views": 14400,
        },
    ],
}

CHARACTERS: list[dict[str, Any]] = [
    {"category": "anime", "name": "Satoru Gojo", "bio": "Six Eyes sorcerer whose presence rewrites the battlefield.", "image": "gojo.jpg"},
    {"category": "anime", "name": "Eren Yeager", "bio": "A surveyor whose revenge arc outruns his own humanity.", "image": "eren.jpg"},
    {"category": "anime", "name": "Anya Forger", "bio": "Telepathic six-year-old with no filter and perfect instincts.", "image": "anya.jpg"},
    {"category": "anime", "name": "Thorfinn Karlsson", "bio": "Viking heir who learns revenge is the least interesting revenge.", "image": "thorfinn.jpg"},
    {"category": "gaming", "name": "The Nameless King", "bio": "Final boss whose moveset is a complete art history.", "image": "nameless-king.jpg"},
    {"category": "gaming", "name": "Wolf (Sekiro)", "bio": "A shinobi missing an arm and most of his past.", "image": "wolf.jpg"},
    {"category": "gaming", "name": "Palico Chef", "bio": "The only NPC you genuinely trust with your ingredients.", "image": "palico.jpg"},
    {"category": "movies", "name": "Kaneda", "bio": "Bike courier, reluctant revolutionary, permanent legend.", "image": "kaneda.jpg"},
    {"category": "movies", "name": "Hugh Glass", "bio": "Survivor of a journey the film refuses to let you enjoy.", "image": "hugh-glass.jpg"},
    {"category": "tv-shows", "name": "Mark Scout", "bio": "Officially severed. Unofficially still working.", "image": "mark-scout.jpg"},
    {"category": "tv-shows", "name": "Carmy Berzatto", "bio": "Chef, manager, and the least stable person in the kitchen.", "image": "carmy.jpg"},
    {"category": "k-pop", "name": "Seong-jin", "bio": "Leader energy, composed vocals, lethal stage presence.", "image": "seongjin.jpg"},
    {"category": "comics", "name": "Peter Parker", "bio": "Photographer, wall-crawler, eternal teenager.", "image": "spider-man.jpg"},
    {"category": "manga", "name": "Eikichi Sawamura", "bio": "Delinquent turned prodigious striker.", "image": "sawamura.jpg"},
    {"category": "cosplay", "name": "The Armoured Cosplayer", "bio": "Fourteen months, one motorcycle, zero regrets.", "image": "armoured-cosplayer.jpg"},
]

MERCHANDISE: list[dict[str, Any]] = [
    {"category": "anime", "name": "Blue Lock jersey replica", "tag": "apparel", "upcoming": False, "desc": "Official-style replica with heat-pressed crest."},
    {"category": "anime", "name": "Frieren staff replica", "tag": "prop", "upcoming": True, "desc": "Limited resin staff, ships next quarter."},
    {"category": "anime", "name": "Frieren blind box series", "tag": "figure", "upcoming": True, "desc": "Eight figures, one secret colourway."},
    {"category": "gaming", "name": "Elden Ring collector's steelbook", "tag": "collector", "upcoming": False, "desc": "Metal case, lenticular art, 120 pages of artbook."},
    {"category": "gaming", "name": "Palworld plush keychain", "tag": "accessory", "upcoming": False, "desc": "Twelve centimetres of questionable ethics."},
    {"category": "gaming", "name": "Indie games zine vol. 3", "tag": "print", "upcoming": True, "desc": "Risograph zine interviewing twelve dev teams."},
    {"category": "movies", "name": "Past Lives poster print", "tag": "art", "upcoming": False, "desc": "Numbered 18x24 print on 200gsm cotton paper."},
    {"category": "movies", "name": "Kaneda jacket patch set", "tag": "accessory", "upcoming": False, "desc": "Four embroidered patches, iron-on backing."},
    {"category": "tv-shows", "name": "Lumon mug", "tag": "homeware", "upcoming": False, "desc": "BPA-free, dishwasher safe, deeply unsettling."},
    {"category": "tv-shows", "name": "The Bear apron", "tag": "apparel", "upcoming": True, "desc": "Cotton twill apron with an embroidered kitchen door."},
    {"category": "k-pop", "name": "Concert lightstick (official)", "tag": "accessory", "upcoming": True, "desc": "Official synced lightstick for the next tour."},
    {"category": "k-pop", "name": "Album photobook", "tag": "print", "upcoming": False, "desc": "Hardcover photobook, 180 pages, foil title."},
    {"category": "comics", "name": "Indie graphic novel bundle", "tag": "print", "upcoming": False, "desc": "Four debut graphic novels in a slipcase."},
    {"category": "comics", "name": "Blank variant cover sleeve", "tag": "collector", "upcoming": False, "desc": "Acid-free boards for protecting blank covers."},
    {"category": "manga", "name": "Manga panel grid reference pack", "tag": "print", "upcoming": False, "desc": "A3 reference sheet for inking layouts."},
    {"category": "manga", "name": "Screen tone sample set", "tag": "art", "upcoming": True, "desc": "40 assorted tone sheets for digital artists."},
    {"category": "cosplay", "name": "EVA foam starter bundle", "tag": "prop", "upcoming": False, "desc": "Two foam sheets, worbla, contact cement, cap."},
    {"category": "cosplay", "name": "Heat-resistant wig tool kit", "tag": "hair", "upcoming": False, "desc": "Curling wand, setting spray, pins and a heat mat."},
    {"category": "cosplay", "name": "Convention prop repair kit", "tag": "prop", "upcoming": True, "desc": "Everything needed to fix a snapped edge the night before."},
]

EVENTS: list[dict[str, Any]] = [
    {
        "name": "Anime Expo 2026",
        "city": "Los Angeles",
        "lat": 34.0015,
        "lng": -118.4065,
        "start": TODAY + dt.timedelta(days=28),
        "end": TODAY + dt.timedelta(days=31),
        "category": "anime",
        "url": "https://anime-expo.org/tickets",
        "desc": "The largest anime convention in North America.",
    },
    {
        "name": "Japan Expo Paris",
        "city": "Paris",
        "lat": 48.8566,
        "lng": 2.3522,
        "start": TODAY + dt.timedelta(days=60),
        "end": TODAY + dt.timedelta(days=64),
        "category": "anime",
        "url": "https://www.japan-expo-paris.com/en/",
        "desc": "Manga, anime, k-pop and cosplay across four halls.",
    },
    {
        "name": "PAX West",
        "city": "Seattle",
        "lat": 47.6062,
        "lng": -122.3321,
        "start": TODAY + dt.timedelta(days=14),
        "end": TODAY + dt.timedelta(days=17),
        "category": "gaming",
        "url": "https://www.paxsite.com/west",
        "desc": "Tabletop, esports and free play.",
    },
    {
        "name": "EVO 2026",
        "city": "Las Vegas",
        "lat": 36.1699,
        "lng": -115.1398,
        "start": TODAY + dt.timedelta(days=45),
        "end": TODAY + dt.timedelta(days=48),
        "category": "gaming",
        "url": "https://www.evogames.com/",
        "desc": "Fighting game tournament of record size.",
    },
    {
        "name": "Seoul K-Pop Festival",
        "city": "Seoul",
        "lat": 37.5665,
        "lng": 126.9780,
        "start": TODAY + dt.timedelta(days=7),
        "end": TODAY + dt.timedelta(days=8),
        "category": "k-pop",
        "url": "https://www.seoulconcertfestival.com/",
        "desc": "Six stages, thirty acts, one very loud weekend.",
    },
    {
        "name": "New York Comic Con",
        "city": "New York",
        "lat": 40.7580,
        "lng": -73.9855,
        "start": TODAY + dt.timedelta(days=21),
        "end": TODAY + dt.timedelta(days=24),
        "category": "comics",
        "url": "https://www.nycomiccon.com/",
        "desc": "Panels, cosplay competitions and the main hall.",
    },
    {
        "name": "Manga Barcelona",
        "city": "Barcelona",
        "lat": 41.3874,
        "lng": 2.1686,
        "start": TODAY + dt.timedelta(days=35),
        "end": TODAY + dt.timedelta(days=36),
        "category": "manga",
        "url": "https://www.mangabarna.com/",
        "desc": "Guests, publishers and a full cosplay contest.",
    },
    {
        "name": "London Comic Con Winter",
        "city": "London",
        "lat": 51.5074,
        "lng": -0.1278,
        "start": TODAY + dt.timedelta(days=10),
        "end": TODAY + dt.timedelta(days=11),
        "category": "cosplay",
        "url": "https://www.comicconlondon.com/",
        "desc": "Two days of cosplay awards and stalls.",
    },
    {
        "name": "Tokyo Comic Market 108",
        "city": "Tokyo",
        "lat": 35.6812,
        "lng": 139.7671,
        "start": TODAY + dt.timedelta(days=50),
        "end": TODAY + dt.timedelta(days=53),
        "category": "manga",
        "url": "https://comiket.co.jp/",
        "desc": "Doujinshi, cosplay and the biggest queue in the world.",
    },
    {
        "name": "Symphony of Anime Film Concert",
        "city": "Chicago",
        "lat": 41.8781,
        "lng": -87.6298,
        "start": TODAY + dt.timedelta(days=40),
        "end": TODAY + dt.timedelta(days=40),
        "category": "movies",
        "url": "https://example.org/symphony-anime",
        "desc": "Anime scores performed by a full orchestra.",
    },
]

FAQS: list[dict[str, Any]] = [
    {
        "question": "What fandoms does Fan Hub Plus cover?",
        "answer": (
            "We cover eight fandoms: Anime, Gaming, Movies, TV Shows, K-Pop, Comics, Manga and "
            "Cosplay. Open the Categories menu to jump into any of them, or filter the content "
            "feed by category."
        ),
        "keywords": ["fandoms", "categories", "what do you cover", "genres", "sections"],
        "priority": 100,
    },
    {
        "question": "How do bookmarks work?",
        "answer": (
            "Sign in, open any content item, character or merchandise entry and hit Bookmark. "
            "Your saved list lives at 'My bookmarks' in your profile menu, and you can add a "
            "private note to each one."
        ),
        "keywords": ["bookmark", "save", "favourite", "favorite", "my list"],
        "priority": 90,
    },
    {
        "question": "How do I rate content?",
        "answer": (
            "On any content page there is a rating widget: a 5-star scale for quality, and a "
            "thumbs up / thumbs down toggle for a quick reaction. One rating per item, and you "
            "can switch between the two scales at any time."
        ),
        "keywords": ["rate", "rating", "stars", "thumbs", "review", "score"],
        "priority": 90,
    },
    {
        "question": "How do I find events near me?",
        "answer": (
            "Use the Events page and pass your location as near=lat,lng with a radius_km value, "
            "or filter by city. Results within your radius show the exact distance in km, sorted "
            "by start date."
        ),
        "keywords": ["events", "convention", "near me", "location", "con", "expo", "radius"],
        "priority": 80,
    },
    {
        "question": "How do I submit fan content?",
        "answer": (
            "Registered fans can submit articles, fan art write-ups or event recaps from the "
            "Submissions page. A moderator reviews every submission, and you can track the "
            "approve/reject status under 'My submissions'."
        ),
        "keywords": ["submit", "submission", "contribute", "post", "moderation", "review"],
        "priority": 70,
    },
]


# ------------------------------------------------------------------ helpers
async def _get_by(session: AsyncSession, model, **filters):
    stmt = select(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return (await session.execute(stmt)).scalars().first()


async def _count(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar() or 0)


# ------------------------------------------------------------------- seeding
async def seed_users(session: AsyncSession) -> dict[str, User]:
    """1 admin + 3 registered users (idempotent, keyed on email)."""
    created: dict[str, User] = {}
    now = dt.datetime.now(dt.timezone.utc)

    admin = await _get_by(session, User, email=settings.seed_admin_email)
    if admin is None:
        admin = User(
            name="Aiko Tanaka",
            email=settings.seed_admin_email,
            password_hash=hash_password(settings.seed_admin_password),
            role=UserRole.ADMIN,
            is_email_verified=True,
            last_login_at=now,
        )
        session.add(admin)
        await session.flush()
        logger.info("seeded_admin", extra={"email": admin.email})
    created["admin"] = admin

    fan_profiles = [
        ("Yuki Sato", "anime", ["anime", "manga", "cosplay"]),
        ("Marcus Reid", "gaming", ["gaming", "tv-shows"]),
        ("Priya Nair", "movies", ["movies", "k-pop", "comics"]),
    ]
    emails = settings.seed_user_email_list
    for index, (name, handle, favourites) in enumerate(fan_profiles):
        email = emails[index] if index < len(emails) else f"fan{index}@fanhubplus.dev"
        user = await _get_by(session, User, email=email)
        if user is None:
            user = User(
                name=name,
                email=email,
                password_hash=hash_password(settings.seed_user_password),
                role=UserRole.REGISTERED,
                is_email_verified=True,
                last_login_at=now,
            )
            session.add(user)
            await session.flush()
            session.add(
                UserPreference(
                    user_id=user.id,
                    favorite_categories=sorted(favourites),
                    display_prefs={"theme": "dark", "language": "en", "compact_cards": False},
                )
            )
            logger.info("seeded_user", extra={"email": email, "role": "registered"})
        created[handle] = user

    await session.commit()
    return created


async def seed_categories(session: AsyncSession) -> dict[str, Category]:
    result: dict[str, Category] = {}
    for payload in CATEGORIES:
        category = await _get_by(session, Category, slug=payload["slug"])
        if category is None:
            category = Category(**payload)
            session.add(category)
            await session.flush()
            logger.info("seeded_category", extra={"slug": payload["slug"]})
        result[payload["slug"]] = category
    await session.commit()
    return result


async def _resolve_tags(session: AsyncSession, names: list[str]) -> list[Tag]:
    """Get-or-create Tag rows for tag names (matches content_service._resolve_tags)."""
    wanted = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not wanted:
        return []
    existing = (
        (await session.execute(select(Tag).where(Tag.name.in_(wanted))))
        .scalars()
        .all()
    )
    by_name = {tag.name: tag for tag in existing}
    for name in wanted:
        if name not in by_name:
            tag = Tag(name=name)
            session.add(tag)
            by_name[name] = tag
    await session.flush()
    return [by_name[name] for name in wanted]


async def seed_content(
    session: AsyncSession, categories: dict[str, Category], users: dict[str, User]
) -> list[Content]:
    created: list[Content] = []
    admin = users["admin"]

    for slug, items in CONTENT_SEED.items():
        category = categories[slug]
        for item in items:
            existing = await _get_by(session, Content, title=item["title"])
            if existing is not None:
                created.append(existing)
                continue
            content = Content(
                category_id=category.id,
                title=item["title"],
                type=item["type"],
                description=item["description"],
                body_rich_text=item.get("body"),
                media_url=item.get("media_url"),
                release_date=dt.date(item["year"], random.randint(1, 12), random.randint(1, 28)),
                view_count=item["views"],
                popularity_score=popularity_service.compute_popularity_score(
                    item["views"], round(random.uniform(3.2, 4.8), 1), random.randint(5, 400),
                    dt.date(item["year"], 6, 1),
                ),
                status=ContentStatus.PUBLISHED,
                created_by=admin.id,
            )
            content.tags = await _resolve_tags(session, item["tags"])
            session.add(content)
            created.append(content)
    await session.commit()
    logger.info("seeded_content", extra={"count": len(created)})
    return created


async def seed_characters(
    session: AsyncSession, categories: dict[str, Category]
) -> list[Character]:
    created: list[Character] = []
    for item in CHARACTERS:
        existing = await _get_by(session, Character, name=item["name"])
        if existing is not None:
            created.append(existing)
            continue
        character = Character(
            category_id=categories[item["category"]].id,
            name=item["name"],
            bio=item["bio"],
            image_url=f"https://cdn.fanhubplus.dev/characters/{item['image']}",
            view_count=random.randint(200, 45_000),
        )
        session.add(character)
        created.append(character)
    await session.commit()
    logger.info("seeded_characters", extra={"count": len(created)})
    return created


async def seed_merchandise(
    session: AsyncSession, categories: dict[str, Category]
) -> list[Merchandise]:
    created: list[Merchandise] = []
    for item in MERCHANDISE:
        existing = await _get_by(session, Merchandise, name=item["name"])
        if existing is not None:
            created.append(existing)
            continue
        merchandise = Merchandise(
            category_id=categories[item["category"]].id,
            name=item["name"],
            description=item["desc"],
            image_url="https://cdn.fanhubplus.dev/merch/placeholder.jpg",
            tag=item["tag"],
            is_upcoming=item["upcoming"],
            release_date=(
                (TODAY + dt.timedelta(days=random.randint(30, 240))).isoformat()
                if item["upcoming"]
                else (TODAY - dt.timedelta(days=random.randint(10, 400))).isoformat()
            ),
            view_count=random.randint(50, 18_000),
        )
        session.add(merchandise)
        created.append(merchandise)
    await session.commit()
    logger.info("seeded_merchandise", extra={"count": len(created)})
    return created


async def seed_events(session: AsyncSession, categories: dict[str, Category]) -> list[Event]:
    created: list[Event] = []
    for item in EVENTS:
        existing = await _get_by(session, Event, name=item["name"])
        if existing is not None:
            created.append(existing)
            continue
        event = Event(
            name=item["name"],
            city=item["city"],
            lat=item["lat"],
            lng=item["lng"],
            start_date=item["start"],
            end_date=item["end"],
            ticket_url=item["url"],
            description=item["desc"],
            category_id=categories[item["category"]].id,
        )
        session.add(event)
        created.append(event)
    await session.commit()
    logger.info("seeded_events", extra={"count": len(created)})
    return created


async def seed_faqs(session: AsyncSession) -> list[ChatbotFaq]:
    created: list[ChatbotFaq] = []
    for item in FAQS:
        existing = await _get_by(session, ChatbotFaq, question=item["question"])
        if existing is not None:
            created.append(existing)
            continue
        faq = ChatbotFaq(
            question=item["question"],
            answer=item["answer"],
            keywords=item["keywords"],
            priority=item["priority"],
            is_active=True,
        )
        session.add(faq)
        created.append(faq)
    await session.commit()
    logger.info("seeded_faqs", extra={"count": len(created)})
    return created


async def seed_engagement(
    session: AsyncSession,
    users: dict[str, User],
    content: list[Content],
    characters: list[Character],
    merchandise: list[Merchandise],
) -> None:
    """A little ratings/bookmark/submission/feedback history so the dashboard,
    moderation queue and admin stats are not empty on a fresh database."""
    from app.db.models.bookmark import Bookmark, BookmarkTarget
    from app.db.models.user import User as UserModel

    # ``users`` is keyed by "admin" plus one entry per seeded fan (see
    # ``seed_users``). Take every non-admin user instead of repeating the fan
    # keys here, so renaming a seeded profile cannot raise KeyError.
    fans = [user for key, user in users.items() if key != "admin"]
    if not fans:
        logger.warning("seed_engagement_no_fans")
        return

    # Ratings: mixed scales, deterministic per user/content pair.
    for index, item in enumerate(content):
        for offset, fan in enumerate(fans):
            if (index + offset) % 4 == 0:
                continue
            existing = await _get_by(session, Rating, user_id=fan.id, content_id=item.id)
            if existing is not None:
                continue
            if (index + offset) % 5 == 0:
                session.add(
                    Rating(
                        user_id=fan.id,
                        content_id=item.id,
                        scale=RatingScale.THUMBS,
                        value=1 if offset % 2 == 0 else -1,
                    )
                )
            else:
                session.add(
                    Rating(
                        user_id=fan.id,
                        content_id=item.id,
                        scale=RatingScale.STARS,
                        value=random.randint(3, 5),
                    )
                )

    # Bookmarks across all three target types.
    targets = (
        [(BookmarkTarget.CONTENT, item.id, item.title) for item in content[:12]]
        + [(BookmarkTarget.CHARACTER, item.id, item.name) for item in characters[:6]]
        + [(BookmarkTarget.MERCHANDISE, item.id, item.name) for item in merchandise[:6]]
    )
    for offset, (target_type, target_id, _title) in enumerate(targets):
        fan = fans[offset % len(fans)]
        existing = await _get_by(
            session, Bookmark, user_id=fan.id, content_type=target_type, content_id=target_id
        )
        if existing is not None:
            continue
        session.add(
            Bookmark(
                user_id=fan.id,
                content_type=target_type,
                content_id=target_id,
                note=random.choice([None, "Must revisit", "Perfect gift", "Study this later"]),
            )
        )

    # Submissions in each moderation state.
    submissions = [
        (fans[0], "Photo essay from the autumn convention", "I shot 300 photos at the anime con and narrowed it down to 12 that actually tell a story. Feedback on the sequencing would be helpful before I publish it.", SubmissionStatus.PENDING, None),
        (fans[1], "A tier list nobody asked for", "I ranked every boss fight in the past decade by pure aesthetics. It is a terrible metric and I stand by it completely. The list is in the body of this submission and spans three sections.", SubmissionStatus.PENDING, None),
        (fans[2], "Cosplay build diary: month six", "Month six of an armour build and the shoulder plates finally sit right. Documenting the process because the tutorials I found all skipped the hard part.", SubmissionStatus.APPROVED, "Great write-up, publishing this week."),
    ]
    for fan, title, body, status, note in submissions:
        if await _get_by(session, FanSubmission, title=title) is not None:
            continue
        session.add(
            FanSubmission(
                user_id=fan.id,
                title=title,
                body=body,
                status=status,
                review_note=note,
                reviewed_by=users["admin"].id if status != SubmissionStatus.PENDING else None,
            )
        )

    # Feedback, including one from an anonymous visitor (user_id is NULL).
    feedback_rows = [
        (fans[0], FeedbackType.SUGGESTION, "Could the content filter support filtering by voice actor? Would love to find every role a favourite actor played.", FeedbackStatus.OPEN, None),
        (fans[1], FeedbackType.BUG, "The alpha sort on the content page looks case-insensitive which is great, but it also sorts numbers before letters, which is probably not what I expected.", FeedbackStatus.REVIEWED, "Confirmed, will document the behaviour in the filter tooltip."),
        (None, FeedbackType.QUERY, "Do you plan to support Korean language for the K-Pop section? I am not a programmer but I would happily write translations if that helps.", FeedbackStatus.OPEN, None),
    ]
    for fan, ftype, message, status, note in feedback_rows:
        if await _get_by(session, Feedback, message=message) is not None:
            continue
        session.add(
            Feedback(
                user_id=fan.id if fan else None,
                type=ftype,
                message=message,
                status=status,
                admin_note=note,
            )
        )

    await session.commit()
    logger.info(
        "seeded_engagement",
        extra={
            "ratings": await _count(session, Rating),
            "bookmarks": await _count(session, Bookmark),
            "submissions": await _count(session, FanSubmission),
            "feedback": await _count(session, Feedback),
        },
    )


async def seed_cache_counters(users: dict[str, User]) -> None:
    """Prime the Redis counters the admin dashboard reads (DAU / category views)."""
    from app.core.redis_client import get_cache, stats_key

    cache = await get_cache()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    await cache.incr(stats_key("active_users", today), len(users) + 3, ex=86_400)
    for index, category in enumerate(CATEGORIES):
        await cache.incr(stats_key("category", category["slug"]), 120 - index * 9)
    await cache.incr(stats_key("chatbot_messages", today), 24)
    await cache.incr(stats_key("chatbot_sessions", today), 9)
    logger.info("seeded_cache_counters", extra={"backend": cache.kind})


# ---------------------------------------------------------------------- main
async def _truncate(session) -> None:
    """Delete every row so the seed starts from a known-empty schema.

    ``TRUNCATE ... RESTART IDENTITY CASCADE`` in one statement: the FK graph spans
    ten parents, and CASCADE clears the children without ordering them by hand.
    """
    statements = ", ".join(
        f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)
    )
    logger.warning("seed_reset_truncating_all_tables")
    await session.execute(
        text(f"TRUNCATE TABLE {statements} RESTART IDENTITY CASCADE")
    )
    await session.commit()


async def main(reset: bool = False) -> int:
    configure_logging()
    logger.info("seed_start", extra={"env": settings.app_env, "reset": reset})

    async with async_session_maker() as session:
        if reset:
            await _truncate(session)
        users = await seed_users(session)
        categories = await seed_categories(session)
        content = await seed_content(session, categories, users)
        characters = await seed_characters(session, categories)
        merchandise = await seed_merchandise(session, categories)
        events = await seed_events(session, categories)
        faqs = await seed_faqs(session)
        await seed_engagement(session, users, content, characters, merchandise)
        await seed_cache_counters(users)

        summary = {
            "users": await _count(session, User),
            "categories": await _count(session, Category),
            "content": await _count(session, Content),
            "characters": await _count(session, Character),
            "merchandise": await _count(session, Merchandise),
            "events": await _count(session, Event),
            "faqs": len(faqs),
        }

    await dispose_engine()

    line = "=" * 66
    print(f"\n{line}\n  Fan Hub Plus - seed complete\n{line}")
    for key, value in summary.items():
        print(f"  {key:<14} {value}")
    print(f"\n  Demo credentials (plaintext, hashed on insert):")
    print(f"    ADMIN      {settings.seed_admin_email}  /  {settings.seed_admin_password}")
    for email in settings.seed_user_email_list:
        print(f"    REGISTERED {email}  /  {settings.seed_user_password}")
    print(f"\n  Try:  curl -X POST http://localhost:8000{settings.api_v1_prefix}/auth/login \\")
    print(f"           -H 'Content-Type: application/json' \\")
    print(f"           -d '{{\"email\": \"{settings.seed_admin_email}\", \"password\": \"{settings.seed_admin_password}\"}}'")
    print(f"{line}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(reset="--reset" in sys.argv[1:])))
