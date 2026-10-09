import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.barber_directory import BarberDirectory

router = APIRouter(prefix="/directory", tags=["Barber Directory"])

# Contact data and sector labels supplied in Marino's directory.
# This list does not create registered barber accounts or payment connections.
DIRECTORY_ENTRIES = [
    {
        "name": "Gentlemen007 Barber Shop",
        "address": "278 Rue Sherbrooke O, Montréal, QC H2X 1X9",
        "phone": "+14388605859",
        "sector": "Downtown"
    },
    {
        "name": "La Baraque Du Barbier",
        "address": "4828 R. Saint-Denis, Montréal, QC H2J 2L6",
        "phone": "+15148458423",
        "sector": "Plateau-Mont-Royal"
    },
    {
        "name": "Notre Barbier",
        "address": "1201 R. Notre Dame O, Montréal, QC H3C 0B1",
        "phone": "+14383759414",
        "sector": "Griffintown"
    },
    {
        "name": "Génération & Cutz Barbier Verdun Barbershop",
        "address": "4619 Rue Wellington, Montréal, QC H4G 1X1",
        "phone": "+15142080291",
        "sector": "Verdun"
    },
    {
        "name": "The Common Room barbershop",
        "address": "2290 Av. Union, Montréal, QC H3A 2C3",
        "phone": "+15148435551",
        "sector": "Downtown"
    },
    {
        "name": "La Section Barbershop",
        "address": "1118 Rue Sainte-Catherine Ouest 211 2nd floor, Montréal, QC H3B 5K2",
        "phone": "+14384992516",
        "sector": "Downtown"
    },
    {
        "name": "La Section Barbershop",
        "address": "777 Blvd Robert-Bourassa Ste 105, Montreal, QC H3C 3Z7",
        "phone": "+14388335409",
        "sector": "Old Montreal"
    },
    {
        "name": "ganabarber",
        "address": "2000 Rue Peel, Montréal, QC H3A 1T1",
        "phone": "+15148178035",
        "sector": "Downtown"
    },
    {
        "name": "Amir barber shop",
        "address": "2005 R. Saint-Denis, Montréal, QC H2X 3K7",
        "phone": "+14389252229",
        "sector": "Plateau-Mont-Royal"
    },
    {
        "name": "Les Barbiers",
        "address": "2292 Avenue du Mont-Royal E, Montréal, QC H2H 1K6",
        "phone": "+15145267630",
        "sector": "Plateau-Mont-Royal"
    },
    {
        "name": "POPSTAR STUDIO BARBERSHOP",
        "address": "1831 Avenue du Mont-Royal E, Montréal, QC H2H 1J2",
        "phone": "+15148174900",
        "sector": "Plateau-Mont-Royal"
    },
    {
        "name": "Signature Cuts Men's Haircuts & Barber Shop",
        "address": "4122 R. Saint-Denis, Montréal, QC H2W 2M5",
        "phone": "+15148087362",
        "sector": "Plateau-Mont-Royal"
    },
    {
        "name": "Salon Maniac Griffintown",
        "address": "1810 R. Notre Dame O, Montréal, QC H3J 1M5",
        "phone": "+14383877575",
        "sector": "Griffintown"
    },
    {
        "name": "Upscale Barbershop",
        "address": "305 Rue Peel, Montréal, QC H3C 3R9",
        "phone": "+14382209990",
        "sector": "Griffintown"
    },
    {
        "name": "Hiraya Barbershop",
        "address": "2325 Rue Centre Ste 101, Montreal, QC H3K 1J6",
        "phone": "+14389250821",
        "sector": "Griffintown"
    },
    {
        "name": "Beardlington Barbershop Verdun",
        "address": "3850 Rue Wellington, Montréal, QC H4G 1V2",
        "phone": "+15147661466",
        "sector": "Verdun"
    },
    {
        "name": "Taki Barbier - Barbier Verdun - Barbershop",
        "address": "4236 Rue Wellington, Montréal, QC H4G 1W2",
        "phone": "+15142142223",
        "sector": "Verdun"
    },
    {
        "name": "Jack Of Fades",
        "address": "4812 Rue de Verdun, Verdun, QC H4G 1N1",
        "phone": "+15149703843",
        "sector": "Verdun"
    },
    {
        "name": "UNIQ Barbershop",
        "address": "106 R. Saint Viateur Ouest, Montréal, QC H2T 2L1",
        "phone": "+15142719202",
        "sector": "Mile End"
    },
    {
        "name": "Fade'ology",
        "address": "5020 Av. du Parc, Montréal, QC H2V 4E8",
        "phone": "+14384481047",
        "sector": "Mile End"
    },
    {
        "name": "Hollywood fairmount salon de barbier",
        "address": "18 Av. Fairmount O, Montréal, QC H2T 2M1",
        "phone": "+15144315793",
        "sector": "Mile End"
    },
    {
        "name": "Casanova barbier",
        "address": "56 Rue Jean-Talon O, Montréal, QC H2R 2W7",
        "phone": "+15142272366",
        "sector": "Little Italy"
    },
    {
        "name": "Saber barbier",
        "address": "7103 R. Drolet, Montréal, QC H2R 1T3",
        "phone": "+14383083228",
        "sector": "Little Italy"
    },
    {
        "name": "QOTW BARBIERS",
        "address": "6754 Boul. Saint-Laurent, Montréal, QC H2S 3C7",
        "phone": "+14389239290",
        "sector": "Little Italy"
    },
    {
        "name": "Maverick Barbier",
        "address": "173 Rue Saint-Zotique Est, Montréal, QC H2S 1K9",
        "phone": "+14388258034",
        "sector": "Little Italy"
    },
    {
        "name": "Diamonds Barbershop",
        "address": "777 Rue Legendre E, Montréal, QC H2M 1H1",
        "phone": "+15143899777",
        "sector": "Ahuntsic"
    },
    {
        "name": "Salon Joe & Sergio",
        "address": "9775 Bd de l'Acadie, Montréal, QC H4N 0C6",
        "phone": "+15148843777",
        "sector": "Ahuntsic"
    },
    {
        "name": "Barbier Mat Cuts",
        "address": "1050 Rue Sauvé E, Montréal, QC H2C 1Z6",
        "phone": "+15149928741",
        "sector": "Ahuntsic"
    },
    {
        "name": "L'Original Barbier",
        "address": "3324 Rue Jean-Talon E, Montréal, QC H2A 1W5",
        "phone": "+14386222318",
        "sector": "Villeray / Saint-Michel"
    },
    {
        "name": "Abdou BarberShop",
        "address": "3530 Rue Jean-Talon E, Montréal, QC H2A 1X2",
        "phone": "+14389908696",
        "sector": "Villeray / Saint-Michel"
    },
    {
        "name": "360 LUXE BARBERSHOP",
        "address": "7706 Rue St-Hubert, Montréal, QC H2R 2N8",
        "phone": "+15142700001",
        "sector": "Villeray"
    },
    {
        "name": "BARBA",
        "address": "1650 Rue Villeray, Montréal, QC H2E 1H4",
        "phone": "+15147210914",
        "sector": "Villeray"
    },
    {
        "name": "Barbier Du Coin",
        "address": "3304 Bd Rosemont, Montréal, QC H1X 1K2",
        "phone": "+15147210251",
        "sector": "Rosemont"
    },
    {
        "name": "Primo barbershop",
        "address": "1306 Rue Bélanger, Montréal, QC H2G 1A1",
        "phone": "+15142720002",
        "sector": "Rosemont"
    },
    {
        "name": "Barbier LaChast Montréal",
        "address": "3762 Rue Masson, Montréal, QC H1X 1S6",
        "phone": "+14382299190",
        "sector": "Rosemont"
    },
    {
        "name": "QUBA BARBERSHOP",
        "address": "5885 Rue Sherbrooke O, Montréal, QC H4A 1X6",
        "phone": "+15142405196",
        "sector": "NDG"
    },
    {
        "name": "Faded Studio Barbershop",
        "address": "5065 Ch. Queen Mary, Montréal, QC H3W 1X4",
        "phone": "+15144302752",
        "sector": "Côte-des-Neiges / NDG"
    },
    {
        "name": "Fovero Barbershop NDG",
        "address": "6570 Av. Somerled, Côte-des-Neiges - Notre-Dame-de-Grâce, QC H4V 1S9",
        "phone": "+15143486570",
        "sector": "NDG"
    },
    {
        "name": "The Barber Shop LaSalle",
        "address": "8740 Boul. Newman, Montréal, QC H8N 1X9",
        "phone": "+15143632273",
        "sector": "LaSalle"
    },
    {
        "name": "Barbershop 911",
        "address": "7622 Boul. Newman, LaSalle, QC H8N 1X7",
        "phone": "+15143659111",
        "sector": "LaSalle"
    },
    {
        "name": "Fade Factory Barbershop",
        "address": "8410 Pass. Angrignon, LaSalle, QC H8N 2W9",
        "phone": "+15145953233",
        "sector": "LaSalle"
    },
    {
        "name": "Kustom Barbershop",
        "address": "1048 Boulevard Décarie, Saint-Laurent, QC H4L 3M2",
        "phone": "+15147478181",
        "sector": "Saint-Laurent"
    },
    {
        "name": "Le Baron Barbier Saint-Laurent",
        "address": "730 Boulevard Marcel-Laurin, Saint-Laurent, QC H4M 2M2",
        "phone": "+15143315276",
        "sector": "Saint-Laurent"
    },
    {
        "name": "Empire Barbershop",
        "address": "3119 Boulevard Côte-Vertu, Saint-Laurent, QC H4R 2M3",
        "phone": "+15143321111",
        "sector": "Saint-Laurent"
    },
    {
        "name": "Studio Cuttin Edge",
        "address": "7350 Boulevard des Galeries d'Anjou, Anjou, QC H1M 1W8",
        "phone": "+15143522888",
        "sector": "Anjou"
    },
    {
        "name": "Barbier Anjou",
        "address": "7075 Boulevard Louis-H. Lafontaine, Anjou, QC H1M 2X2",
        "phone": "+15143534444",
        "sector": "Anjou"
    },
    {
        "name": "The Classic Barber Montreal",
        "address": "6090 Boulevard Robert, Saint-Léonard, QC H1P 1M1",
        "phone": "+15143251122",
        "sector": "Saint-Léonard"
    },
    {
        "name": "Barbershop St-Léonard",
        "address": "8330 Boulevard Lacordaire, Saint-Léonard, QC H1R 3Y6",
        "phone": "+15143283333",
        "sector": "Saint-Léonard"
    },
    {
        "name": "Le Barbier Sauvage",
        "address": "8595 Boul Langelier, Montréal, QC H1P 2C6",
        "phone": "+15142421428",
        "sector": "Saint-Léonard"
    },
    {
        "name": "DC Barber Saint Leonard",
        "address": "4729 Bd Métropolitain E, Montréal, QC H1R 0C1",
        "phone": "+14383792227",
        "sector": "Saint-Léonard"
    },
    {
        "name": "H&S BARBER'S",
        "address": "6044 Rue Jean-Talon E, Saint-Léonard, QC H1S 3A9",
        "phone": "+14384597795",
        "sector": "Saint-Léonard"
    },
    {
        "name": "Papï Barber",
        "address": "5358 Rue Jean-Talon E, Saint-Léonard, QC H1S 1L5",
        "phone": "+15149220237",
        "sector": "Saint-Léonard"
    },
    {
        "name": "Salon de Barbier Karat Barbershop",
        "address": "1596 Rue Fleury E, Montréal, QC H2C 1S8",
        "phone": "+15142683060",
        "sector": "Ahuntsic-Cartierville"
    },
    {
        "name": "HighStyle Barbershop",
        "address": "2525 Rue Fleury E, Montréal, QC H2B 1L6",
        "phone": "+15147063264",
        "sector": "Ahuntsic-Cartierville"
    },
    {
        "name": "2Strong Barbershop",
        "address": "2561 Boul Henri-Bourassa E, Montréal, QC H2B 1V4",
        "phone": "+14383803380",
        "sector": "Montreal-North"
    },
    {
        "name": "Barbier S.D",
        "address": "653 R. de Louvain Est, Montréal, QC H2M 1A7",
        "phone": "+14383998930",
        "sector": "Ahuntsic"
    },
    {
        "name": "Les Salons Golden Mens Barbershop Cartierville",
        "address": "6007 Boul Gouin O, Montréal, QC H4J 2M8",
        "phone": "+14389928101",
        "sector": "Cartierville"
    },
    {
        "name": "Barbier des Artistes",
        "address": "3490 Rue Hochelaga, Montréal, QC H1W 1H5",
        "phone": "+15149702560",
        "sector": "Hochelaga-Maisonneuve"
    },
    {
        "name": "La Coupe Masculine",
        "address": "1874 Av. d'Orléans, Montréal, QC H1W 3R5",
        "phone": "+14388773426",
        "sector": "Hochelaga-Maisonneuve"
    },
    {
        "name": "adam barbier",
        "address": "3225B Rue Ontario E, Montréal, QC H1W 1P3",
        "phone": "+15145989797",
        "sector": "Hochelaga-Maisonneuve"
    },
    {
        "name": "le Barbier",
        "address": "2003 Rue de Chambly, Montréal, QC H1W 3J3",
        "phone": "+15146003423",
        "sector": "Hochelaga-Maisonneuve"
    },
    {
        "name": "Salon Barbier Nabil",
        "address": "3545 A Rue Ontario E, Montréal, QC H1W 1R6",
        "phone": "+14389944280",
        "sector": "Hochelaga-Maisonneuve"
    },
    {
        "name": "Fade47 salon de coiffure",
        "address": "1252 Av Dollard, LaSalle, QC H8N 2P2",
        "phone": "+12636600003",
        "sector": "LaSalle"
    },
    {
        "name": "Prime fadez",
        "address": "2685 Rue Allard, Montréal, QC H4E 2L7",
        "phone": "+12635585465",
        "sector": "LaSalle / Ville-Émard"
    },
    {
        "name": "GS FADES",
        "address": "8529 Rue Hélène, LaSalle, QC H8N 1Z3",
        "phone": "+15149494443",
        "sector": "LaSalle"
    },
    {
        "name": "Roi De Klipz Barbier",
        "address": "1667 Av Dollard, LaSalle, QC H8N 1T7",
        "phone": "+15143651185",
        "sector": "LaSalle"
    },
    {
        "name": "Jack Of Fades",
        "address": "2480 Rue Lapierre Ste 204, Lasalle, QC H8N 2W9",
        "phone": "+15149703843",
        "sector": "LaSalle"
    },
    {
        "name": "Haven Barbershop",
        "address": "3289 Rue Saint-Jacques, Montréal, QC H4C 1G8",
        "phone": "+15148466636",
        "sector": "Saint-Henri"
    },
    {
        "name": "DIMENSION BARBERSHOP",
        "address": "4030 Saint Ambroise St #154, Montreal, QC H4C 2E1",
        "phone": "+15146993180",
        "sector": "Saint-Henri"
    },
    {
        "name": "Salon Barbe Blanche",
        "address": "3733 R. Notre Dame O, Montréal, QC H4C 1P8",
        "phone": "+15147976454",
        "sector": "Saint-Henri"
    },
    {
        "name": "Colours Montreal",
        "address": "4710 Saint Ambroise St #120, Montreal, QC H4C 0C9",
        "phone": "+15145644247",
        "sector": "Saint-Henri"
    },
    {
        "name": "CRISP Barbershop Pointe-Saint-Charles",
        "address": "2022 Rue Centre, Montréal, QC H3K 1J3",
        "phone": "+15149343300",
        "sector": "Pointe-Saint-Charles"
    },
    {
        "name": "VerTex88 barbershop",
        "address": "385 Rue Sherbrooke O, Montréal, QC H3A 1B5",
        "phone": "+15146274433",
        "sector": "Downtown / Westmount border"
    },
    {
        "name": "CRISP Barbershop Village",
        "address": "1188 Rue Ontario E, Montréal, QC H2K 3K4",
        "phone": "+15145233300",
        "sector": "The Village"
    },
    {
        "name": "Fade Atelier",
        "address": "1368 Ave Greene, Westmount, QC H3Z 2B1",
        "phone": "+15149073440",
        "sector": "Westmount"
    },
    {
        "name": "El West Barbershop",
        "address": "342A Av. Victoria, Westmount, QC H3Z 2M8",
        "phone": "+14389887497",
        "sector": "Westmount"
    },
    {
        "name": "Mama's Boy Barbershop",
        "address": "5125 Rue Sherbrooke O, Montréal, QC H4A 1T2",
        "phone": "+14383806644",
        "sector": "NDG / Westmount border"
    },
    {
        "name": "ice barbershop",
        "address": "5265 Rue Sherbrooke O, Montréal, QC H4A 1V1",
        "phone": "+15146907920",
        "sector": "NDG / Westmount border"
    },
    {
        "name": "Le Barbier de Westmount",
        "address": "4441 Rue Sainte-Catherine, Westmount, QC H3Z 1R5",
        "phone": "+15149335501",
        "sector": "Westmount"
    },
    {
        "name": "Esquire Barbier Barber Shop",
        "address": "1284 Av. Bernard, Outremont, QC H2V 1V9",
        "phone": "+15143600417",
        "sector": "Outremont"
    },
    {
        "name": "Salon Coupe d'Or",
        "address": "1562 Av. Van Horne, Outremont, QC H2V 1L5",
        "phone": "+15147720553",
        "sector": "Outremont"
    },
    {
        "name": "Scotch & Scissors Barbershop",
        "address": "1009 Av. Van Horne, Outremont, QC H2V 1J4",
        "phone": "+15142842887",
        "sector": "Outremont"
    },
    {
        "name": "Barbier514",
        "address": "3570 Rue Bélair, Montréal, QC H2A 2B2",
        "phone": "+15147181173",
        "sector": "Parc-Extension"
    },
    {
        "name": "Cutz 'N Roses Barbershop",
        "address": "810 Rue Jarry E, Montréal, QC H2P 1W5",
        "phone": "+15143601756",
        "sector": "Ahuntsic / Parc-Extension"
    },
    {
        "name": "FlyOff Barbershop Lachine",
        "address": "2525 Rue Provost, Lachine, QC H8S 1R2",
        "phone": "+14383994581",
        "sector": "Lachine"
    },
    {
        "name": "MINT Barbershop",
        "address": "945 Rue Notre Dame, Lachine, QC H8S 2C1",
        "phone": "+15143006468",
        "sector": "Lachine"
    },
    {
        "name": "Fundamentum Barbershop lachine",
        "address": "1055 Rue Notre Dame, Lachine, QC H8S 2C2",
        "phone": "+14385298598",
        "sector": "Lachine"
    },
    {
        "name": "Mazz Barbier West Island",
        "address": "14820 Boul. de Pierrefonds, Pierrefonds, QC H9H 4Y6",
        "phone": "+15146262424",
        "sector": "Pierrefonds"
    },
    {
        "name": "West Island Barber Shop - Coiffures Pour Hommes",
        "address": "3285 Bd des Sources, Dollard-des-Ormeaux, QC H9B 2N8",
        "phone": "+15146833466",
        "sector": "Dollard-des-Ormeaux"
    },
    {
        "name": "Barbier Belmont Barbershop, Kirkland, West Island",
        "address": "110 Rue du Barry, Kirkland, QC H9H 4P8",
        "phone": "+15144266565",
        "sector": "Kirkland"
    },
    {
        "name": "The One Three Barber Studio",
        "address": "3 Rue Sunnydale, Dollard-des-Ormeaux, QC H9B 1E1",
        "phone": "+15144211113",
        "sector": "Dollard-des-Ormeaux"
    },
    {
        "name": "DETAILS BARBIER BARBERSHOP",
        "address": "14280 Boul Gouin O, Pierrefonds, QC H8Z 1Y1",
        "phone": "+15149135922",
        "sector": "Pierrefonds"
    },
    {
        "name": "Barbier Chairman's Barber",
        "address": "4505 Bd Saint-Charles, Pierrefonds, QC H9H 3C7",
        "phone": "+15146245577",
        "sector": "Pierrefonds"
    },
    {
        "name": "Mâle Alpha Barbier",
        "address": "13084 R. Sherbrooke E, Montréal, QC H1A 3W2",
        "phone": "+15146670582",
        "sector": "Rivière-des-Prairies"
    },
    {
        "name": "Majestic design",
        "address": "1489 Bd Saint-Jean-Baptiste, Montréal, QC H1B 5J9",
        "phone": "+15149696641",
        "sector": "Pointe-aux-Trembles"
    },
    {
        "name": "Crystal Cutz Barber Shop",
        "address": "12411 Boulevard Rodolphe-Forget, Montreal, QC H1E 0A2",
        "phone": "+15144973111",
        "sector": "Montreal-North / East"
    },
    {
        "name": "VANYX Attitude",
        "address": "11901 Rue Notre Dame E, Pointe-aux-Trembles, QC H1B 2Y4",
        "phone": "+15142653575",
        "sector": "Pointe-aux-Trembles"
    },
    {
        "name": "DNA BARBERSHOP",
        "address": "2911 Rue Allard, Montréal, QC H4E 2M4",
        "phone": "+14389221776",
        "sector": "Ville-Émard"
    },
    {
        "name": "La Baraque du Barbier l",
        "address": "4536a Rue Wellington, Montréal, QC H4G 1W7",
        "phone": "+15144612282",
        "sector": "Verdun"
    }
]


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", value).strip().lower()


def sector_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalized_text(value)).strip("-")


def seed_directory() -> int:
    """Insert missing listings only. Restarts preserve edits and hidden entries."""
    values = []
    for entry in DIRECTORY_ENTRIES:
        identity = normalized_text(entry["name"]) + "|" + normalized_text(entry["address"])
        values.append({
            **entry,
            "entry_key": hashlib.sha256(identity.encode()).hexdigest(),
            "sector_key": sector_slug(entry["sector"]),
            "is_listed": True,
            "created_at": datetime.utcnow(),
        })
    with SessionLocal() as db:
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            insert = postgres_insert
        elif dialect == "sqlite":
            insert = sqlite_insert
        else:
            raise RuntimeError("Directory requires PostgreSQL or SQLite.")
        statement = insert(BarberDirectory).values(values).on_conflict_do_nothing(
            index_elements=["entry_key"]
        ).returning(BarberDirectory.id)
        inserted = len(db.execute(statement).scalars().all())
        db.commit()
        return inserted


@router.get("/sectors")
def list_sectors(db: Session = Depends(get_db)):
    rows = (
        db.query(BarberDirectory.sector_key, BarberDirectory.sector, func.count(BarberDirectory.id))
        .filter(BarberDirectory.is_listed.is_(True))
        .group_by(BarberDirectory.sector_key, BarberDirectory.sector)
        .order_by(BarberDirectory.sector)
        .all()
    )
    return {
        "total": sum(count for _, _, count in rows),
        "sectors": [{"key": key, "name": name, "count": count} for key, name, count in rows],
    }


@router.get("")
def list_barber_shops(
    sector: Optional[str] = Query(default=None, min_length=1, max_length=150),
    db: Session = Depends(get_db),
):
    query = db.query(BarberDirectory).filter(BarberDirectory.is_listed.is_(True))
    if sector is not None:
        key = sector_slug(sector)
        query = query.filter(BarberDirectory.sector_key == key)
        if not query.first():
            raise HTTPException(status_code=404, detail="No listings found for this sector.")
    rows = query.order_by(BarberDirectory.sector, BarberDirectory.name, BarberDirectory.id).all()
    return {
        "total": len(rows),
        "barber_shops": [
            {
                "id": row.id,
                "name": row.name,
                "address": row.address,
                "phone": row.phone,
                "sector": row.sector,
                "sector_key": row.sector_key,
                "call_url": "tel:" + row.phone,
            }
            for row in rows
        ],
    }