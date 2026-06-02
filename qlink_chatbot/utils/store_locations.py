from __future__ import annotations

import re


STORE_SOURCE_URL = "https://www.jaipurrugs.com/in/contact-us"


JAIPUR_RUGS_STORE_LOCATIONS = [
    {
        "name": "Jaipur Retail Store - Head Office",
        "city": "Jaipur",
        "country": "India",
        "address": "G-250, Mansarovar Industrial Area, Jaipur, Rajasthan, India 302020",
        "phone": "+91 141 3987400",
        "email": "shop@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm (IST)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Jaipur Gallery",
        "city": "Jaipur",
        "country": "India",
        "address": "Kanota Courtyard, Hotel Narain Niwas Palace, Narayan Singh Road, Jaipur 302004",
        "phone": "+91 7412060021",
        "email": "shop@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm (IST)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Delhi Retail Store",
        "city": "Delhi",
        "country": "India",
        "address": "Shop No. 298-299, Near Metro Pillar SP-32, Mehrauli-Gurgaon Road, Sultanpur, New Delhi 110030",
        "phone": "+91 7230005522",
        "email": "delhi@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm (IST)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Mumbai Retail Store - Lower Parel",
        "city": "Mumbai",
        "country": "India",
        "address": "Empire Complex, 414, Senapati Bapat Marg, Lower Parel, Mumbai 400013",
        "phone": "+91 9799228116 | +91 7230005538",
        "email": "mumbai@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm (IST)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Mumbai Retail Store - Andheri",
        "city": "Mumbai",
        "country": "India",
        "address": "Laxmi Industrial Estate, 21 C-D, Ground Floor, New Link Road, Andheri West, Mumbai 400053",
        "phone": "(+91) 9351227137",
        "email": "mumbai@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm (IST)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Bengaluru Retail Store",
        "city": "Bengaluru",
        "country": "India",
        "address": "1st Floor, 1147, K.P.Icon, 12th Main, HAL 2nd Stage, Indiranagar, Bengaluru 560008",
        "phone": "+91 7849916323",
        "email": "bengaluru@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm (IST)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Ahmedabad Retail Store",
        "city": "Ahmedabad",
        "country": "India",
        "address": "Bajrang Lifestyle BLA 101-102, P V Enclave, Sindhu Bhavan Marg, Bodakdev, Ahmedabad 380054",
        "phone": "+91 9920121119",
        "email": "ahmedabad@jaipurrugs.com",
        "timing": "Mon - Sat: 10:00am - 7:00pm | Sun: Closed",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Chennai Retail Store",
        "city": "Chennai",
        "country": "India",
        "address": "Supreme Living, Plot No. 320, Valluvar Kottam High Road, Nungambakkam, Chennai 600034",
        "phone": "+91 9257033044",
        "email": "chennai@jaipurrugs.com",
        "timing": "Mon - Sun: 10:30am - 7:30pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Pune Retail Store",
        "city": "Pune",
        "country": "India",
        "address": "Unit 3&4, Omicron Commerz, Off North Main Road Koregaon Park, NX, Mundhwa, Pune 411036",
        "phone": "+91 9251985915",
        "email": "pune@jaipurrugs.com",
        "timing": "Mon - Fri: 10:00am - 9:30pm | Sat - Sun: 10:00am - 10:00pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Raipur Retail Store",
        "city": "Raipur",
        "country": "India",
        "address": "Ground floor, SS Turning Point, Near Shanti Sarovar, Kachna, Raipur 493770",
        "phone": "+91 9257058410",
        "email": "raipur@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 8:00pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Kolkata Retail Store",
        "city": "Kolkata",
        "country": "India",
        "address": "Ground Floor, Chatterjee International Center, 33A, Jawaharlal Nehru Road, Park Street area, Kolkata 700071",
        "phone": "+91 7665433115",
        "email": "kolkata@jaipurrugs.com",
        "timing": "Monday - Sunday: 10:00am - 8:00am",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Other Cities Quick Contact",
        "city": "Other Cities",
        "country": "India",
        "address": "Coimbatore, Kerala, Hyderabad",
        "phone": "+91 9257058408 (Coimbatore/Kerala) | +91 9251985911 (Hyderabad)",
        "email": "shop@jaipurrugs.com",
        "timing": "",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Milan Retail Store",
        "city": "Milan",
        "country": "Italy",
        "address": "Piazzale Luigi Cadorna, 4, 20123 Milano MI, Italy",
        "phone": "+39 0238262167",
        "email": "milan@jaipurrugs.com",
        "timing": "Mon - Sat: 10:00am - 7:00pm (CET)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "London Retail Gallery",
        "city": "London",
        "country": "United Kingdom",
        "address": "1/23, Chelsea Harbour Design Centre, Chelsea Harbour, London SW10 0XE",
        "phone": "+44 2045976964",
        "email": "london@jaipurrugs.com",
        "timing": "Mon - Fri: 9:30am - 5:30pm (GMT)",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Singapore Retail Store",
        "city": "Singapore",
        "country": "Singapore",
        "address": "68A - 69A, Amoy Street, Singapore 069887",
        "phone": "+65 97291342",
        "email": "singapore@jaipurrugs.com",
        "timing": "Mon - Sat: 9:30am - 6:30pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Samara Retail Store",
        "city": "Samara",
        "country": "Russia",
        "address": "23, Michurina Street, Samara, Russia",
        "phone": "+7 846 97 377 00 | +7 939 702 30 30",
        "email": "info@jrsamara.com",
        "timing": "",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Shanghai Retail Store",
        "city": "Shanghai",
        "country": "China",
        "address": "C212, Wending Living Plaza, Wending Road 258, Xuhui District, Shanghai",
        "phone": "+86 2154650598",
        "email": "china@jaipurrugs.com",
        "timing": "Mon - Sun: 10:00am - 6:00pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Beijing Retail Store",
        "city": "Beijing",
        "country": "China",
        "address": "No. C210-310, No.5, Wanhong Road, Chaoyang District, Beijing",
        "phone": "+86 13810096375",
        "email": "jiabuercarpet@qq.com",
        "timing": "Mon - Sun: 9:30am - 6:30pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Dubai Regional Office",
        "city": "Dubai",
        "country": "United Arab Emirates",
        "address": "Unit A02, Alserkal Avenue, 17th Street, Al Quoz 01, Dubai, UAE",
        "phone": "+971 43988780",
        "email": "dubai@jaipurrugs.com",
        "timing": "Mon - Thu: 10:00am - 7:00pm | Fri - Sun: 10:00am - 9:00pm",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "KSA Contact",
        "city": "KSA",
        "country": "Saudi Arabia",
        "address": "",
        "phone": "+966 55 6403405",
        "email": "ahmed.a@jaipurrugs.com",
        "timing": "",
        "source": STORE_SOURCE_URL,
    },
    {
        "name": "Acworth Head Office",
        "city": "Acworth",
        "country": "USA",
        "address": "Jaipur Living Inc. 1800 Cherokee Parkway, Acworth, GA 30102",
        "phone": "888-676-7330",
        "email": "support@jaipurliving.com",
        "timing": "Mon - Fri: 9:30am - 5:30pm (GMT)",
        "source": STORE_SOURCE_URL,
    },
]


_CITY_ALIASES = {
    "bangalore": "bengaluru",
    "new delhi": "delhi",
    "delhi ncr": "delhi",
    "lower parel": "mumbai",
    "andheri": "mumbai",
    "uae": "dubai",
    "united arab emirates": "dubai",
    "ksa": "ksa",
    "saudi": "ksa",
    "saudi arabia": "ksa",
    "usa": "acworth",
    "us": "acworth",
    "america": "acworth",
    "coimbatore": "other cities",
    "kerala": "other cities",
    "hyderabad": "other cities",
    "milano": "milan",
}

_GENERIC_LOCATION_WORDS = {
    "address",
    "all",
    "available",
    "city",
    "direction",
    "directions",
    "in",
    "location",
    "locations",
    "near",
    "showroom",
    "showrooms",
    "store",
    "stores",
    "timing",
    "timings",
}


def _normalize(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s-]", " ", (value or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return _CITY_ALIASES.get(normalized, normalized)


def search_store_locations(query: str = "") -> dict:
    """Return Jaipur Rugs store locations that match the user's city/country query."""
    normalized_query = _normalize(query)
    query_terms = [
        _CITY_ALIASES.get(part, part)
        for part in normalized_query.split()
        if part and part not in _GENERIC_LOCATION_WORDS
    ]

    if (
        not normalized_query
        or "all" in normalized_query.split()
        or "every" in normalized_query.split()
        or not query_terms
    ):
        return {
            "source": STORE_SOURCE_URL,
            "stores": JAIPUR_RUGS_STORE_LOCATIONS,
        }

    matches = []
    for store in JAIPUR_RUGS_STORE_LOCATIONS:
        searchable = _normalize(" ".join([
            store.get("name", ""),
            store.get("city", ""),
            store.get("country", ""),
            store.get("address", ""),
        ]))
        if normalized_query in searchable or any(term in searchable for term in query_terms):
            matches.append(store)

    return {
        "source": STORE_SOURCE_URL,
        "stores": matches,
    }
