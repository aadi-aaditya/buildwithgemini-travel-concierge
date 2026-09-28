"""
Seed script to populate Firestore with sample destination data for the Travel Concierge agent.
"""
from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-02-52babdffede5"

SEED_DESTINATIONS = [
    {
        "destination_id": "kyoto-japan",
        "name": "Kyoto Cultural Sanctuary",
        "city": "Kyoto",
        "country": "Japan",
        "category": "Culture",
        "description": "Ancient temples, traditional tea houses, and tranquil bamboo groves nestled in historic Japan.",
        "price_per_night": 280.0,
        "rating": 4.9,
        "highlights": ["Arashiyama Bamboo Grove", "Fushimi Inari Shrine", "Traditional Ryokan Stay"],
    },
    {
        "destination_id": "santorini-greece",
        "name": "Santorini Sunset Retreat",
        "city": "Santorini",
        "country": "Greece",
        "category": "Beach",
        "description": "Dramatic cliffside views of the Aegean Sea with iconic white-washed architecture and world-class wine.",
        "price_per_night": 350.0,
        "rating": 4.8,
        "highlights": ["Oia Sunset Walk", "Volcanic Wine Tasting", "Red Beach Cruise"],
    },
    {
        "destination_id": "banff-canada",
        "name": "Banff Mountain Wilderness",
        "city": "Banff",
        "country": "Canada",
        "category": "Adventure",
        "description": "Turquoise glacial lakes, pristine alpine forests, and rugged Rocky Mountain peak explorations.",
        "price_per_night": 220.0,
        "rating": 4.7,
        "highlights": ["Lake Louise Kayaking", "Johnston Canyon Hike", "Gondola Ridge View"],
    },
    {
        "destination_id": "amalfi-italy",
        "name": "Amalfi Coast Hideaway",
        "city": "Amalfi",
        "country": "Italy",
        "category": "Luxury",
        "description": "Picturesque coastal villages, lemon orchards, and exquisite Mediterranean seaside dining.",
        "price_per_night": 420.0,
        "rating": 4.9,
        "highlights": ["Path of the Gods Hike", "Positano Coastal Boat Tour", "Limoncello Tasting"],
    },
    {
        "destination_id": "serengeti-tanzania",
        "name": "Serengeti Safari Lodge",
        "city": "Serengeti",
        "country": "Tanzania",
        "category": "Adventure",
        "description": "Unrivaled wildlife safaris across endless savanna plains, home to the Great Migration.",
        "price_per_night": 510.0,
        "rating": 4.95,
        "highlights": ["Game Drives", "Hot Air Balloon Safari", "Maasai Cultural Visit"],
    },
]


def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection("destinations")

    print(f"Seeding Firestore collection 'destinations' in project '{PROJECT_ID}'...")
    for item in SEED_DESTINATIONS:
        doc_ref = collection.document(item["destination_id"])
        doc_ref.set(item)
        print(f"  - Seeded: {item['name']} ({item['city']}, {item['country']})")

    print("Firestore seeding completed successfully!")


if __name__ == "__main__":
    seed_database()
