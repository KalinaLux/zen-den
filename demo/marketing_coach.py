"""
Marketing Coach — "Marketing for Beginners" backend for the Zen Den app.

Helps non-technical business owners understand and run advertising through
template-driven plans, keyword suggestions, budget advice, performance
translation, and a marketing calendar. No external dependencies required.
"""

import html
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

log = logging.getLogger("zen.coach")

# ---------------------------------------------------------------------------
# Data directory (PyInstaller-aware)
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path.home() / "Library" / "Application Support" / "ZenDen"
    else:
        base = Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUSINESS_TYPES = {
    "wedding_venue":    {"label": "Wedding Venue",    "emoji": "\U0001f490"},
    "vacation_rental":  {"label": "Vacation Rental",  "emoji": "\U0001f3d6\ufe0f"},
    "restaurant":       {"label": "Restaurant",       "emoji": "\U0001f37d\ufe0f"},
    "ecommerce":        {"label": "E-Commerce Store",  "emoji": "\U0001f6d2"},
    "local_service":    {"label": "Local Service",    "emoji": "\U0001f527"},
    "real_estate":      {"label": "Real Estate",      "emoji": "\U0001f3e0"},
    "fitness":          {"label": "Fitness / Gym",    "emoji": "\U0001f4aa"},
    "beauty_salon":     {"label": "Beauty Salon",     "emoji": "\U0001f485"},
    "photography":      {"label": "Photography",      "emoji": "\U0001f4f7"},
    "consulting":       {"label": "Consulting",       "emoji": "\U0001f4bc"},
    "nonprofit":        {"label": "Nonprofit",        "emoji": "\U0001f49a"},
    "other":            {"label": "Other",            "emoji": "\U0001f310"},
}

GOAL_OPTIONS = {
    "more_inquiries":   "Get More Inquiries",
    "more_bookings":    "Increase Bookings",
    "brand_awareness":  "Build Brand Awareness",
    "website_traffic":  "Drive Website Traffic",
    "phone_calls":      "Get More Phone Calls",
    "app_installs":     "Drive App Installs",
    "local_visits":     "Increase Local Visits",
    "online_sales":     "Boost Online Sales",
}

INDUSTRY_BENCHMARKS = {
    "wedding_venue":   {"avg_cpc": 2.50, "avg_ctr": 3.5, "avg_conv_rate": 2.0, "suggested_daily_budget_min": 15, "suggested_daily_budget_max": 50},
    "vacation_rental": {"avg_cpc": 1.20, "avg_ctr": 4.0, "avg_conv_rate": 3.0, "suggested_daily_budget_min": 10, "suggested_daily_budget_max": 40},
    "restaurant":      {"avg_cpc": 1.50, "avg_ctr": 5.0, "avg_conv_rate": 4.0, "suggested_daily_budget_min": 10, "suggested_daily_budget_max": 30},
    "ecommerce":       {"avg_cpc": 1.10, "avg_ctr": 2.5, "avg_conv_rate": 2.5, "suggested_daily_budget_min": 15, "suggested_daily_budget_max": 60},
    "local_service":   {"avg_cpc": 3.00, "avg_ctr": 4.5, "avg_conv_rate": 5.0, "suggested_daily_budget_min": 10, "suggested_daily_budget_max": 35},
    "real_estate":     {"avg_cpc": 2.80, "avg_ctr": 3.0, "avg_conv_rate": 1.5, "suggested_daily_budget_min": 20, "suggested_daily_budget_max": 70},
    "fitness":         {"avg_cpc": 1.80, "avg_ctr": 3.8, "avg_conv_rate": 4.5, "suggested_daily_budget_min": 10, "suggested_daily_budget_max": 35},
    "beauty_salon":    {"avg_cpc": 1.40, "avg_ctr": 4.2, "avg_conv_rate": 5.0, "suggested_daily_budget_min": 8,  "suggested_daily_budget_max": 25},
    "photography":     {"avg_cpc": 1.60, "avg_ctr": 3.2, "avg_conv_rate": 2.5, "suggested_daily_budget_min": 10, "suggested_daily_budget_max": 30},
    "consulting":      {"avg_cpc": 4.00, "avg_ctr": 2.8, "avg_conv_rate": 3.0, "suggested_daily_budget_min": 15, "suggested_daily_budget_max": 50},
    "nonprofit":       {"avg_cpc": 1.00, "avg_ctr": 3.5, "avg_conv_rate": 2.0, "suggested_daily_budget_min": 5,  "suggested_daily_budget_max": 20},
    "other":           {"avg_cpc": 2.00, "avg_ctr": 3.0, "avg_conv_rate": 2.5, "suggested_daily_budget_min": 10, "suggested_daily_budget_max": 40},
}

KEYWORD_TEMPLATES = {
    "wedding_venue": [
        "destination wedding {location}",
        "wedding venue {location}",
        "luxury wedding venue {location}",
        "outdoor wedding {location}",
        "private wedding venue {location}",
        "rainforest wedding venue",
        "unique wedding venues near me",
        "beach wedding {location}",
        "garden wedding venue {location}",
        "all-inclusive wedding venue {location}",
        "intimate wedding venue {location}",
        "wedding reception venue {location}",
        "affordable wedding venue {location}",
        "rustic wedding venue {location}",
        "best wedding venues {location}",
        "elopement venue {location}",
        "wedding packages {location}",
        "wedding venue with waterfall",
        "destination wedding planner {location}",
        "romantic wedding venue {location}",
    ],
    "vacation_rental": [
        "vacation rental {location}",
        "airbnb {location}",
        "cabin rental {location}",
        "beach house {location}",
        "villa rental {location}",
        "holiday home {location}",
        "pet-friendly vacation rental {location}",
        "family vacation rental {location}",
        "luxury vacation rental {location}",
        "weekend getaway {location}",
        "short-term rental {location}",
        "cottage rental {location}",
        "vacation home with pool {location}",
        "romantic getaway {location}",
        "mountain cabin {location}",
        "lake house rental {location}",
        "secluded cabin {location}",
        "group vacation rental {location}",
        "monthly rental {location}",
        "best places to stay {location}",
    ],
    "restaurant": [
        "best restaurants {location}",
        "restaurants near me {location}",
        "{type} food {location}",
        "dinner reservations {location}",
        "brunch {location}",
        "catering {location}",
        "private dining {location}",
        "farm to table {location}",
        "romantic dinner {location}",
        "family restaurant {location}",
        "outdoor dining {location}",
        "best lunch {location}",
        "food delivery {location}",
        "fine dining {location}",
        "happy hour {location}",
        "birthday dinner {location}",
        "new restaurant {location}",
        "takeout {location}",
    ],
    "ecommerce": [
        "buy {type} online",
        "best {type} shop",
        "{type} store online",
        "affordable {type}",
        "handmade {type}",
        "premium {type}",
        "custom {type}",
        "{type} for sale",
        "shop {type} online",
        "unique {type} gifts",
        "{type} deals",
        "free shipping {type}",
        "best {type} 2025",
        "luxury {type}",
        "cheap {type} online",
        "{type} subscription",
    ],
    "local_service": [
        "{type} {location}",
        "{type} near me",
        "best {type} {location}",
        "affordable {type} {location}",
        "emergency {type} {location}",
        "licensed {type} {location}",
        "{type} services {location}",
        "top rated {type} {location}",
        "{type} repair {location}",
        "{type} installation {location}",
        "same day {type} {location}",
        "cheap {type} {location}",
        "professional {type} {location}",
        "residential {type} {location}",
        "commercial {type} {location}",
    ],
    "real_estate": [
        "homes for sale {location}",
        "houses for sale {location}",
        "real estate agent {location}",
        "buy a house {location}",
        "sell my house {location}",
        "property listings {location}",
        "condos for sale {location}",
        "real estate {location}",
        "luxury homes {location}",
        "first time home buyer {location}",
        "open houses {location}",
        "new construction {location}",
        "investment property {location}",
        "waterfront property {location}",
        "best neighborhoods {location}",
        "real estate market {location}",
        "townhomes for sale {location}",
    ],
    "fitness": [
        "gym {location}",
        "gym near me",
        "personal trainer {location}",
        "fitness classes {location}",
        "yoga studio {location}",
        "crossfit {location}",
        "weight loss program {location}",
        "group fitness {location}",
        "24 hour gym {location}",
        "best gym {location}",
        "pilates {location}",
        "boxing gym {location}",
        "spin class {location}",
        "martial arts {location}",
        "gym membership deals {location}",
        "boot camp fitness {location}",
    ],
    "beauty_salon": [
        "hair salon {location}",
        "beauty salon {location}",
        "nail salon {location}",
        "haircut {location}",
        "balayage {location}",
        "hair color {location}",
        "blowout {location}",
        "best salon {location}",
        "bridal hair {location}",
        "keratin treatment {location}",
        "eyelash extensions {location}",
        "waxing {location}",
        "facial {location}",
        "spa {location}",
        "microblading {location}",
        "hair extensions {location}",
    ],
    "photography": [
        "photographer {location}",
        "wedding photographer {location}",
        "portrait photographer {location}",
        "family photographer {location}",
        "engagement photos {location}",
        "headshot photographer {location}",
        "newborn photographer {location}",
        "event photographer {location}",
        "real estate photographer {location}",
        "boudoir photographer {location}",
        "maternity photographer {location}",
        "senior portraits {location}",
        "photo studio {location}",
        "mini session photographer {location}",
        "elopement photographer {location}",
    ],
    "consulting": [
        "{type} consultant {location}",
        "{type} consulting firm",
        "business consultant {location}",
        "management consulting {location}",
        "marketing consultant {location}",
        "strategy consulting {location}",
        "IT consultant {location}",
        "financial advisor {location}",
        "small business consultant",
        "leadership coaching {location}",
        "executive coaching {location}",
        "business coach {location}",
        "operations consultant {location}",
        "HR consultant {location}",
        "{type} advisory services",
    ],
    "nonprofit": [
        "donate to {type}",
        "{type} charity {location}",
        "volunteer {location}",
        "nonprofit {location}",
        "community organizations {location}",
        "give back {location}",
        "support {type}",
        "charity events {location}",
        "fundraising {location}",
        "help {type} {location}",
        "donate locally {location}",
        "community service {location}",
        "{type} foundation",
        "humanitarian aid {location}",
        "social impact {location}",
    ],
    "other": [
        "{type} {location}",
        "{type} near me",
        "best {type} {location}",
        "affordable {type} {location}",
        "{type} services",
        "top {type} {location}",
        "{type} for sale",
        "{type} reviews",
        "{type} online",
        "professional {type} {location}",
        "local {type} {location}",
        "find {type} {location}",
        "{type} company {location}",
        "reliable {type} {location}",
        "{type} prices {location}",
    ],
}

MARKETING_CALENDAR = [
    {"month": 1, "name": "January", "events": [
        {"name": "New Year's Resolution Season", "types": ["fitness", "consulting", "beauty_salon"],
         "tip": "People are motivated to change. Run 'New Year, New You' campaigns with special January pricing."},
        {"name": "Engagement Season Peak", "types": ["wedding_venue", "photography"],
         "tip": "Most proposals happen Dec\u2013Feb. Your ads should be running NOW to capture couples starting their venue search."},
        {"name": "Winter Travel Planning", "types": ["vacation_rental"],
         "tip": "Families start booking spring break trips. Highlight your availability for March and April."},
    ]},
    {"month": 2, "name": "February", "events": [
        {"name": "Valentine's Day", "types": ["restaurant", "photography", "beauty_salon", "vacation_rental"],
         "tip": "Romance is in the air. Promote couples' experiences, gift certificates, and romantic getaways."},
        {"name": "Wedding Planning Season", "types": ["wedding_venue", "photography"],
         "tip": "Newly engaged couples are actively venue shopping. Showcase your best photos and availability."},
        {"name": "Tax Season Begins", "types": ["consulting", "local_service"],
         "tip": "Small business owners are thinking about finances. Position your services as smart investments."},
    ]},
    {"month": 3, "name": "March", "events": [
        {"name": "Spring Break", "types": ["vacation_rental", "restaurant"],
         "tip": "Last-minute spring break bookings spike. Run urgency ads: 'Limited availability for Spring Break!'"},
        {"name": "Home Improvement Season Starts", "types": ["local_service", "real_estate"],
         "tip": "Homeowners start spring projects. Plumbers, landscapers, painters \u2014 this is your time."},
        {"name": "International Women's Day", "types": ["beauty_salon", "nonprofit", "fitness"],
         "tip": "Run celebratory promotions or community events. Great for social media engagement."},
    ]},
    {"month": 4, "name": "April", "events": [
        {"name": "Earth Day", "types": ["nonprofit", "ecommerce", "restaurant"],
         "tip": "Highlight sustainability efforts. Eco-friendly products and practices resonate now."},
        {"name": "Peak Wedding Booking", "types": ["wedding_venue", "photography"],
         "tip": "Wedding season is approaching fast. Push 'last available dates' messaging to drive urgency."},
        {"name": "Tax Refund Season", "types": ["ecommerce", "fitness", "beauty_salon"],
         "tip": "People have extra money to spend. Run 'Treat Yourself' campaigns."},
    ]},
    {"month": 5, "name": "May", "events": [
        {"name": "Mother's Day", "types": ["restaurant", "beauty_salon", "photography", "ecommerce"],
         "tip": "Gift-giving season. Promote gift cards, special packages, and family portrait sessions."},
        {"name": "Wedding Season Begins", "types": ["wedding_venue", "photography"],
         "tip": "Showcase real weddings at your venue. Social proof is your best ad right now."},
        {"name": "Memorial Day Travel", "types": ["vacation_rental"],
         "tip": "Three-day weekend bookings. If you have availability, run flash sales."},
    ]},
    {"month": 6, "name": "June", "events": [
        {"name": "Peak Wedding Season", "types": ["wedding_venue", "photography"],
         "tip": "You're in peak season. Start promoting 2026/2027 dates for couples still searching."},
        {"name": "Summer Vacation Rush", "types": ["vacation_rental", "restaurant"],
         "tip": "Families are booking summer trips. Target parents on Facebook and Instagram."},
        {"name": "Father's Day", "types": ["restaurant", "ecommerce", "fitness"],
         "tip": "Don't forget Dad. Promote experiential gifts, special menus, and fitness packages."},
    ]},
    {"month": 7, "name": "July", "events": [
        {"name": "Fourth of July", "types": ["vacation_rental", "restaurant"],
         "tip": "Holiday weekend = premium pricing opportunity. Promote special events and packages."},
        {"name": "Summer Fitness Push", "types": ["fitness", "beauty_salon"],
         "tip": "\"Summer body\" searches are still strong. Offer summer membership deals."},
        {"name": "Back-to-School Prep Starts", "types": ["ecommerce", "photography"],
         "tip": "Parents start thinking about school. Senior portraits, school supplies, and family photos."},
    ]},
    {"month": 8, "name": "August", "events": [
        {"name": "Back to School", "types": ["ecommerce", "photography", "restaurant"],
         "tip": "Families are busy and spending. Target parents with convenience-focused messaging."},
        {"name": "Late Summer Travel Deals", "types": ["vacation_rental"],
         "tip": "End-of-summer availability? Run clearance-style pricing to fill remaining dates."},
        {"name": "Fall Planning", "types": ["wedding_venue", "consulting"],
         "tip": "Fall is a popular wedding season. Businesses start Q4 planning too \u2014 be top of mind."},
    ]},
    {"month": 9, "name": "September", "events": [
        {"name": "Fall Wedding Season", "types": ["wedding_venue", "photography"],
         "tip": "Beautiful fall colors = stunning wedding content. Capture and promote everything."},
        {"name": "Back to Routine", "types": ["fitness", "beauty_salon", "consulting"],
         "tip": "People settle into routines. Great time for \"restart\" messaging and September specials."},
        {"name": "Small Business Saturday Prep", "types": ["local_service", "ecommerce", "restaurant"],
         "tip": "Start building your holiday campaign now. Early birds get better ad placement and lower costs."},
    ]},
    {"month": 10, "name": "October", "events": [
        {"name": "Halloween", "types": ["restaurant", "ecommerce", "photography"],
         "tip": "Themed events, products, and photo sessions are wildly popular on social media."},
        {"name": "Holiday Travel Booking", "types": ["vacation_rental"],
         "tip": "Thanksgiving and Christmas travel bookings spike. Get your listings and ads ready."},
        {"name": "Q4 Budget Planning", "types": ["consulting", "local_service"],
         "tip": "Businesses finalize budgets. Position yourself as a must-have for next year."},
    ]},
    {"month": 11, "name": "November", "events": [
        {"name": "Black Friday / Cyber Monday", "types": ["ecommerce", "beauty_salon", "fitness"],
         "tip": "The biggest shopping weekend of the year. Your ads MUST be running. Start early \u2014 people browse before they buy."},
        {"name": "Thanksgiving", "types": ["restaurant", "vacation_rental"],
         "tip": "Promote holiday catering, special menus, and family gathering rentals."},
        {"name": "Engagement Season Begins", "types": ["wedding_venue", "photography"],
         "tip": "Proposals are coming. Get your 'Just Engaged?' campaigns ready to launch Dec 1."},
    ]},
    {"month": 12, "name": "December", "events": [
        {"name": "Holiday Shopping Peak", "types": ["ecommerce", "beauty_salon", "restaurant"],
         "tip": "Gift cards, last-minute deals, and holiday packages. Run ads through Dec 23 at minimum."},
        {"name": "Proposal Season", "types": ["wedding_venue", "photography"],
         "tip": "Christmas and New Year's Eve are the #1 and #2 proposal days. Run warm, emotional ads."},
        {"name": "Year-End Giving", "types": ["nonprofit"],
         "tip": "Most charitable giving happens in December. Run compelling impact stories and matching gift campaigns."},
        {"name": "New Year Travel", "types": ["vacation_rental"],
         "tip": "New Year's Eve getaways book early. If you have availability, promote it heavily."},
    ]},
]

JARGON_DICTIONARY = {
    "cpc": {
        "full_name": "Cost Per Click",
        "explanation": "How much you pay each time someone clicks your ad. Think of it like paying for a visitor to walk into your store.",
        "tip": "Lower is usually better, but super cheap clicks often aren't from real customers.",
    },
    "ctr": {
        "full_name": "Click-Through Rate",
        "explanation": "The percentage of people who saw your ad and actually clicked it. If 100 people see your ad and 3 click, your CTR is 3%.",
        "tip": "Higher is better. A low CTR means your ad isn't grabbing attention \u2014 try different images or headlines.",
    },
    "roas": {
        "full_name": "Return on Ad Spend",
        "explanation": "How much money you made for every dollar you spent on ads. A ROAS of 5 means you earned $5 for every $1 spent.",
        "tip": "Anything above 3 is generally considered good. Below 1 means you're losing money.",
    },
    "conversion": {
        "full_name": "Conversion",
        "explanation": "When someone does the thing you wanted them to do \u2014 fills out a form, makes a purchase, calls you, etc.",
        "tip": "This is the metric that matters most. Clicks are nice, but conversions pay the bills.",
    },
    "impression": {
        "full_name": "Impression",
        "explanation": "One view of your ad. If your ad shows up on someone's screen, that's one impression \u2014 even if they don't click.",
        "tip": "Impressions alone don't mean much. What matters is whether those views turn into clicks and customers.",
    },
    "reach": {
        "full_name": "Reach",
        "explanation": "The number of unique people who saw your ad. Unlike impressions, reach counts each person only once.",
        "tip": "Good for brand awareness campaigns. More reach = more people know you exist.",
    },
    "frequency": {
        "full_name": "Frequency",
        "explanation": "How many times the same person saw your ad on average. A frequency of 3 means each person saw it about 3 times.",
        "tip": "Between 2\u20134 is ideal. Above 7 and people start getting annoyed (ad fatigue).",
    },
    "quality_score": {
        "full_name": "Quality Score",
        "explanation": "Google's rating (1\u201310) of how relevant and useful your ad is. Higher scores mean cheaper clicks and better ad positions.",
        "tip": "Improve it by making sure your ad matches what people are searching for and your landing page delivers on the promise.",
    },
    "ad_rank": {
        "full_name": "Ad Rank",
        "explanation": "Where your ad appears on the page. Position 1 is the top. Your rank depends on your bid and your Quality Score.",
        "tip": "You don't always need position 1 \u2014 position 2 or 3 can be more cost-effective.",
    },
    "bounce_rate": {
        "full_name": "Bounce Rate",
        "explanation": "The percentage of visitors who land on your website and leave without doing anything \u2014 no clicks, no scrolling, nothing.",
        "tip": "A high bounce rate means your landing page isn't matching what your ad promised. Fix the page, not the ad.",
    },
    "landing_page": {
        "full_name": "Landing Page",
        "explanation": "The specific page people see after clicking your ad. It's not your homepage \u2014 it should be a focused page designed to get them to take action.",
        "tip": "A great landing page is the difference between wasting money and getting customers.",
    },
    "retargeting": {
        "full_name": "Retargeting / Remarketing",
        "explanation": "Showing ads to people who already visited your website. Ever looked at shoes online and then seen ads for those exact shoes everywhere? That's retargeting.",
        "tip": "One of the most effective (and affordable) ad strategies. These people already know you.",
    },
    "lookalike_audience": {
        "full_name": "Lookalike Audience",
        "explanation": "A group of new people who are similar to your existing customers. Facebook/Meta is especially good at finding these.",
        "tip": "Give the platform a list of your best customers and it will find more people like them.",
    },
    "ab_testing": {
        "full_name": "A/B Testing",
        "explanation": "Running two versions of an ad to see which one performs better. Like a taste test, but for ads.",
        "tip": "Only change one thing at a time (headline, image, etc.) so you know what actually made the difference.",
    },
    "campaign": {
        "full_name": "Campaign",
        "explanation": "The top-level container for your ads. A campaign has a goal, a budget, and contains ad groups.",
        "tip": "Keep campaigns organized by goal. Don't put 'brand awareness' and 'get bookings' in the same campaign.",
    },
    "ad_group": {
        "full_name": "Ad Group",
        "explanation": "A group of related ads and keywords inside a campaign. Think of it as a folder that organizes your ads by theme.",
        "tip": "Group tightly related keywords together. 'Wedding venue Puerto Rico' and 'destination wedding Caribbean' could be one ad group.",
    },
    "ad_set": {
        "full_name": "Ad Set",
        "explanation": "Meta/Facebook's version of an ad group. It's where you set your targeting, budget, and schedule for a group of ads.",
        "tip": "Create separate ad sets for different audiences so you can see which group responds best.",
    },
    "budget": {
        "full_name": "Budget",
        "explanation": "How much you're willing to spend on your ads, usually set as a daily amount. The platform will try not to exceed this.",
        "tip": "Start small ($10\u201315/day), learn what works, then scale up. You can always increase later.",
    },
    "bid": {
        "full_name": "Bid",
        "explanation": "The maximum amount you're willing to pay for a click or action. You're competing in an auction against other advertisers.",
        "tip": "Most beginners should use automatic bidding and let the platform optimize for you.",
    },
    "keyword": {
        "full_name": "Keyword",
        "explanation": "A word or phrase you want your ad to show up for when someone searches Google. 'Wedding venue Puerto Rico' is a keyword.",
        "tip": "Focus on specific keywords that match what your ideal customer would actually type.",
    },
    "negative_keyword": {
        "full_name": "Negative Keyword",
        "explanation": "A word or phrase you DON'T want your ad to show for. If you're a luxury venue, you might add 'cheap' as a negative keyword.",
        "tip": "Review your search terms weekly and add irrelevant ones as negatives. This saves real money.",
    },
    "search_term": {
        "full_name": "Search Term",
        "explanation": "The actual words someone typed into Google before seeing your ad. This is different from your keyword \u2014 it's what people really searched.",
        "tip": "Check your search terms report regularly. You'll find surprises \u2014 both good keywords to add and bad ones to block.",
    },
    "display_network": {
        "full_name": "Display Network",
        "explanation": "A collection of millions of websites, apps, and videos where your ads can appear as banners or images (not search results).",
        "tip": "Great for brand awareness but generally lower quality clicks than search. Use eye-catching images.",
    },
    "conversion_rate": {
        "full_name": "Conversion Rate",
        "explanation": "The percentage of people who clicked your ad AND completed your desired action. 100 clicks and 3 inquiries = 3% conversion rate.",
        "tip": "Industry average is 2\u20135%. If yours is below 1%, focus on improving your landing page.",
    },
    "cpa": {
        "full_name": "Cost Per Acquisition",
        "explanation": "How much it costs you to get one customer or lead. If you spent $300 and got 3 inquiries, your CPA is $100.",
        "tip": "Compare this to how much a customer is worth to you. $100 per lead for a $50,000 wedding is a great deal.",
    },
    "audience_targeting": {
        "full_name": "Audience Targeting",
        "explanation": "Choosing who sees your ads based on age, location, interests, behavior, and more. Like choosing which neighborhood to put your billboard in.",
        "tip": "Start broad and let the platform learn, then narrow down once you see who's actually converting.",
    },
    "geotargeting": {
        "full_name": "Geotargeting",
        "explanation": "Showing your ads only to people in specific locations \u2014 a city, state, zip code, or even a radius around your business.",
        "tip": "Essential for local businesses. Don't pay for clicks from people 1,000 miles away who will never visit.",
    },
    "pixel": {
        "full_name": "Tracking Pixel",
        "explanation": "A tiny invisible code on your website that tracks what visitors do after clicking your ad. It's how you measure if ads actually lead to bookings.",
        "tip": "Install this BEFORE running ads. Without it, you're flying blind.",
    },
    "roi": {
        "full_name": "Return on Investment",
        "explanation": "How much profit you made compared to how much you spent. Spent $500, made $2,000 in bookings? That's a 300% ROI.",
        "tip": "Always account for your time and costs beyond just ad spend when calculating true ROI.",
    },
    "cpm": {
        "full_name": "Cost Per Mille (Thousand Impressions)",
        "explanation": "How much you pay for 1,000 people to see your ad. Used mostly in brand awareness campaigns.",
        "tip": "If you're paying for impressions, make sure your ad is memorable. A forgettable ad at any price is wasted money.",
    },
}

PLATFORM_RECOMMENDATIONS = {
    "wedding_venue": [
        {"platform": "meta", "priority": 1, "reason": "Instagram is where engaged couples dream about their wedding. Your stunning venue photos will stop them mid-scroll."},
        {"platform": "google", "priority": 2, "reason": "Capture people actively searching for 'wedding venue' + your location. High intent = ready to book."},
        {"platform": "pinterest", "priority": 3, "reason": "Wedding planning central. Promoted pins can reach couples in early planning stages."},
        {"platform": "tiktok", "priority": 4, "reason": "Wedding TikTok is massive. Behind-the-scenes venue tours go viral regularly."},
    ],
    "vacation_rental": [
        {"platform": "google", "priority": 1, "reason": "Travelers search Google first. Be there when someone types 'vacation rental' + your area."},
        {"platform": "meta", "priority": 2, "reason": "Beautiful property photos perform well on Instagram. Target travel enthusiasts and people in feeder markets."},
        {"platform": "tiktok", "priority": 3, "reason": "Property tours and 'hidden gem' content perform incredibly well with younger travelers."},
    ],
    "restaurant": [
        {"platform": "google", "priority": 1, "reason": "'Restaurants near me' is one of the most searched phrases. Combine with Google Business Profile for maximum visibility."},
        {"platform": "meta", "priority": 2, "reason": "Food photos and videos on Instagram drive cravings and reservations. Run ads to locals within 15 miles."},
        {"platform": "tiktok", "priority": 3, "reason": "Food content is king on TikTok. A single viral video can book your restaurant for months."},
    ],
    "ecommerce": [
        {"platform": "google", "priority": 1, "reason": "Google Shopping ads show your products with images and prices directly in search results. Highest purchase intent."},
        {"platform": "meta", "priority": 2, "reason": "Facebook and Instagram shopping features let people buy without leaving the app. Great for impulse purchases."},
        {"platform": "tiktok", "priority": 3, "reason": "TikTok Shop is exploding. Product demos and reviews drive massive sales for the right products."},
        {"platform": "pinterest", "priority": 4, "reason": "People come to Pinterest to discover and plan purchases. Product pins feel native, not like ads."},
    ],
    "local_service": [
        {"platform": "google", "priority": 1, "reason": "When someone's pipe bursts or AC breaks, they Google it. Google Local Services Ads put you at the very top."},
        {"platform": "meta", "priority": 2, "reason": "Build trust with before/after photos and customer reviews. Target homeowners in your service area."},
        {"platform": "nextdoor", "priority": 3, "reason": "Neighbors trust recommendations from neighbors. Local services thrive on Nextdoor."},
    ],
    "real_estate": [
        {"platform": "google", "priority": 1, "reason": "Home buyers start their search on Google. Be there for 'homes for sale in [your city]'."},
        {"platform": "meta", "priority": 2, "reason": "Target people based on life events: just married, new job, growing family. Visual property ads perform well."},
        {"platform": "zillow", "priority": 3, "reason": "Meet buyers where they're already looking. Zillow Premier Agent puts you in front of active searchers."},
    ],
    "fitness": [
        {"platform": "meta", "priority": 1, "reason": "Instagram fitness content drives membership. Show transformations, class energy, and community vibes."},
        {"platform": "google", "priority": 2, "reason": "Capture high-intent searches like 'gym near me' and 'personal trainer [city]'."},
        {"platform": "tiktok", "priority": 3, "reason": "Workout clips, trainer tips, and gym culture content can build a huge local following."},
    ],
    "beauty_salon": [
        {"platform": "meta", "priority": 1, "reason": "Instagram IS the beauty industry. Before-and-after transformations are your best ads."},
        {"platform": "google", "priority": 2, "reason": "When someone needs a haircut or wants balayage, they Google it. Be there."},
        {"platform": "tiktok", "priority": 3, "reason": "Hair and beauty transformations are some of the most-watched content on TikTok."},
    ],
    "photography": [
        {"platform": "meta", "priority": 1, "reason": "Your portfolio IS your marketing. Instagram showcases your work exactly how clients want to see it."},
        {"platform": "google", "priority": 2, "reason": "Capture searches like 'wedding photographer [city]' when people are ready to book."},
        {"platform": "pinterest", "priority": 3, "reason": "Brides and event planners use Pinterest for inspiration. Your photos can lead directly to inquiries."},
    ],
    "consulting": [
        {"platform": "google", "priority": 1, "reason": "Business owners search for consultants on Google. Target specific pain points: 'help scaling my business'."},
        {"platform": "linkedin", "priority": 2, "reason": "The professional network. Target by job title, company size, and industry. Premium audience."},
        {"platform": "meta", "priority": 3, "reason": "Facebook groups and targeted ads can reach small business owners. Share value-first content."},
    ],
    "nonprofit": [
        {"platform": "google", "priority": 1, "reason": "Google Ad Grants gives eligible nonprofits $10,000/month in free search ads. Apply immediately."},
        {"platform": "meta", "priority": 2, "reason": "Emotional storytelling on Facebook and Instagram drives donations. Video performs best."},
        {"platform": "tiktok", "priority": 3, "reason": "Cause-driven content resonates deeply on TikTok, especially with younger donors."},
    ],
    "other": [
        {"platform": "google", "priority": 1, "reason": "Google Search covers almost every type of business. Start here to capture people actively looking for what you offer."},
        {"platform": "meta", "priority": 2, "reason": "Facebook and Instagram let you target very specific audiences. Great for building awareness and getting leads."},
        {"platform": "tiktok", "priority": 3, "reason": "If your business has any visual element, TikTok can reach new audiences incredibly fast."},
    ],
}

# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

_PROFILES_FILE = "coach_profiles.json"


def _profiles_path() -> Path:
    return _data_dir() / _PROFILES_FILE


def load_profiles() -> list:
    path = _profiles_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load profiles: %s", exc)
        return []


def save_profiles(profiles: list):
    path = _profiles_path()
    path.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Saved %d profile(s) to %s", len(profiles), path)


def get_profile(profile_id: str) -> dict | None:
    for p in load_profiles():
        if p.get("id") == profile_id:
            return p
    return None


def create_profile(data: dict) -> dict:
    profiles = load_profiles()
    now = datetime.utcnow().isoformat() + "Z"
    profile = {
        "id": f"biz_{uuid.uuid4().hex[:12]}",
        "name": data.get("name", "My Business"),
        "business_type": data.get("business_type", "other"),
        "website": data.get("website", ""),
        "description": data.get("description", ""),
        "location": data.get("location", ""),
        "monthly_budget": data.get("monthly_budget", 500),
        "goals": data.get("goals", []),
        "target_audience": data.get("target_audience", {}),
        "platforms": data.get("platforms", ["google", "meta"]),
        "website_info": {},
        "marketing_plan": None,
        "created_at": now,
        "updated_at": now,
    }
    profiles.append(profile)
    save_profiles(profiles)
    log.info("Created profile %s for '%s'", profile["id"], profile["name"])
    return profile


def update_profile(profile_id: str, data: dict) -> dict | None:
    profiles = load_profiles()
    for i, p in enumerate(profiles):
        if p.get("id") == profile_id:
            for key, value in data.items():
                if key not in ("id", "created_at"):
                    p[key] = value
            p["updated_at"] = datetime.utcnow().isoformat() + "Z"
            profiles[i] = p
            save_profiles(profiles)
            log.info("Updated profile %s", profile_id)
            return p
    return None


def delete_profile(profile_id: str) -> bool:
    profiles = load_profiles()
    original_count = len(profiles)
    profiles = [p for p in profiles if p.get("id") != profile_id]
    if len(profiles) < original_count:
        save_profiles(profiles)
        log.info("Deleted profile %s", profile_id)
        return True
    return False

# ---------------------------------------------------------------------------
# Website Analyzer
# ---------------------------------------------------------------------------

def analyze_website(url: str) -> dict:
    """Fetch a URL and extract basic marketing-relevant information."""
    if not url or not url.startswith(("http://", "https://")):
        return {"error": "Please provide a valid URL starting with http:// or https://"}

    try:
        req = Request(url, headers={"User-Agent": "ZenDen-MarketingCoach/1.0"})
        with urlopen(req, timeout=10) as resp:
            raw = resp.read(200_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            page_html = raw.decode(charset, errors="replace")
    except (URLError, HTTPError, OSError, ValueError) as exc:
        log.warning("Website fetch failed for %s: %s", url, exc)
        return {"error": f"Couldn't reach the website: {exc}"}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.IGNORECASE | re.DOTALL)
    title = html.unescape(title_match.group(1).strip()) if title_match else ""

    meta_match = re.search(
        r'<meta\s+[^>]*name=["\']description["\']\s+content=["\'](.*?)["\']',
        page_html, re.IGNORECASE,
    )
    if not meta_match:
        meta_match = re.search(
            r'<meta\s+[^>]*content=["\'](.*?)["\']\s+name=["\']description["\']',
            page_html, re.IGNORECASE,
        )
    meta_description = html.unescape(meta_match.group(1).strip()) if meta_match else ""

    text_only = re.sub(r"<script[^>]*>.*?</script>", "", page_html, flags=re.IGNORECASE | re.DOTALL)
    text_only = re.sub(r"<style[^>]*>.*?</style>", "", text_only, flags=re.IGNORECASE | re.DOTALL)
    text_only = re.sub(r"<[^>]+>", " ", text_only)
    text_only = html.unescape(text_only)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    key_phrases = text_only[:500]

    images_found = len(re.findall(r"<img\b", page_html, re.IGNORECASE))
    has_contact_form = bool(re.search(r"<form\b", page_html, re.IGNORECASE))

    social_patterns = [
        r'https?://(?:www\.)?facebook\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?instagram\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?twitter\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?x\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?linkedin\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?pinterest\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?youtube\.com/[^\s"\'<>]+',
        r'https?://(?:www\.)?tiktok\.com/[^\s"\'<>]+',
    ]
    social_links = []
    for pattern in social_patterns:
        social_links.extend(re.findall(pattern, page_html, re.IGNORECASE))
    social_links = list(dict.fromkeys(social_links))  # deduplicate preserving order

    result = {
        "title": title,
        "meta_description": meta_description,
        "key_phrases": key_phrases,
        "images_found": images_found,
        "has_contact_form": has_contact_form,
        "social_links": social_links,
    }
    log.info("Analyzed website %s: title=%r, images=%d", url, title, images_found)
    return result

# ---------------------------------------------------------------------------
# Keyword Suggester
# ---------------------------------------------------------------------------

def suggest_keywords(profile: dict) -> list[dict]:
    """Generate keyword suggestions based on profile data and templates."""
    btype = profile.get("business_type", "other")
    templates = KEYWORD_TEMPLATES.get(btype, KEYWORD_TEMPLATES["other"])
    location = profile.get("location", "")
    name = profile.get("name", "")
    btype_label = BUSINESS_TYPES.get(btype, {}).get("label", btype)
    bench = INDUSTRY_BENCHMARKS.get(btype, INDUSTRY_BENCHMARKS["other"])

    results = []
    for template in templates:
        kw = template.format(location=location, name=name, type=btype_label)
        kw = re.sub(r"\s+", " ", kw).strip()

        word_count = len(kw.split())
        if word_count >= 4:
            competition = "Low"
            relevance = "High"
            cpc_mult = 0.8
            tip = "Longer, more specific keywords often cost less and attract more serious customers."
        elif word_count == 3:
            competition = "Medium"
            relevance = "High"
            cpc_mult = 1.0
            tip = "Good balance of search volume and specificity."
        else:
            competition = "High"
            relevance = "Medium"
            cpc_mult = 1.3
            tip = "Short keywords get lots of searches but are more competitive and expensive."

        if location and location.lower() in kw.lower():
            relevance = "High"
            tip = f"Great local intent \u2014 people searching this are looking specifically in {location}."

        estimated_cpc = round(bench["avg_cpc"] * cpc_mult, 2)

        results.append({
            "keyword": kw,
            "estimated_cpc": f"${estimated_cpc:.2f}",
            "competition": competition,
            "relevance": relevance,
            "tip": tip,
        })

    return results

# ---------------------------------------------------------------------------
# Budget Advisor
# ---------------------------------------------------------------------------

def advise_budget(profile: dict) -> dict:
    """Provide personalized budget recommendations."""
    btype = profile.get("business_type", "other")
    bench = INDUSTRY_BENCHMARKS.get(btype, INDUSTRY_BENCHMARKS["other"])
    monthly = profile.get("monthly_budget", 500)
    location = profile.get("location", "your area")
    name = profile.get("name", "your business")
    goals = profile.get("goals", [])
    platforms = profile.get("platforms", ["google", "meta"])
    btype_label = BUSINESS_TYPES.get(btype, {}).get("label", btype)

    suggested_daily = round((bench["suggested_daily_budget_min"] + bench["suggested_daily_budget_max"]) / 2)
    suggested_monthly = suggested_daily * 30
    minimum_viable = bench["suggested_daily_budget_min"] * 30

    if len(platforms) == 1:
        split = {platforms[0].title(): "100%"}
    elif len(platforms) == 2:
        recs = PLATFORM_RECOMMENDATIONS.get(btype, [])
        p1_name = platforms[0].title()
        p2_name = platforms[1].title()
        p1_priority = next((r["priority"] for r in recs if r["platform"] == platforms[0]), 2)
        p2_priority = next((r["priority"] for r in recs if r["platform"] == platforms[1]), 2)
        if p1_priority < p2_priority:
            split = {p1_name: "60%", p2_name: "40%"}
        elif p2_priority < p1_priority:
            split = {p2_name: "60%", p1_name: "40%"}
        else:
            split = {p1_name: "50%", p2_name: "50%"}
    else:
        primary = platforms[0].title()
        remaining = [p.title() for p in platforms[1:]]
        each_pct = 40 // len(remaining) if remaining else 0
        split = {primary: "60%"}
        for p in remaining:
            split[p] = f"{each_pct}%"

    daily_clicks_low = max(1, int(monthly / 30 / bench["avg_cpc"] * 0.8))
    daily_clicks_high = max(2, int(monthly / 30 / bench["avg_cpc"] * 1.2))
    weekly_convs = max(1, int(daily_clicks_low * 7 * bench["avg_conv_rate"] / 100))

    goal_label = GOAL_OPTIONS.get(goals[0], "results") if goals else "results"

    what_youll_get = (
        f"At ${monthly / 30:.0f}/day on a {btype_label.lower()} in {location}, "
        f"expect roughly {daily_clicks_low}\u2013{daily_clicks_high} clicks daily, "
        f"which could mean about {weekly_convs}\u2013{weekly_convs * 2} {goal_label.lower()} per week. "
        f"Give it 2\u20134 weeks to see a clear pattern."
    )

    scaling_advice = (
        f"Start at ${bench['suggested_daily_budget_min']}/day for 2 weeks. "
        f"If you're seeing {goal_label.lower()}, increase to ${suggested_daily}/day. "
        f"If not, we'll adjust your targeting and ad copy first \u2014 "
        f"throwing more money at a broken ad doesn't help."
    )

    warnings = [
        "Don't spread too thin \u2014 better to dominate one platform than be invisible on three.",
    ]
    if monthly < minimum_viable:
        warnings.append(
            f"Your current budget of ${monthly}/month is below the recommended minimum of "
            f"${minimum_viable}/month for a {btype_label.lower()}. You can still run ads, "
            f"but focus on a single platform and very targeted keywords."
        )
    if len(platforms) > 2:
        warnings.append(
            "Running on more than 2 platforms with a limited budget spreads your impact thin. "
            "Consider starting with your top 2 platforms first."
        )

    return {
        "recommended_daily": f"${suggested_daily}",
        "recommended_monthly": f"${suggested_monthly}",
        "minimum_viable": f"${minimum_viable}/month",
        "budget_split": split,
        "what_youll_get": what_youll_get,
        "scaling_advice": scaling_advice,
        "warnings": warnings,
    }

# ---------------------------------------------------------------------------
# Marketing Plan Generator
# ---------------------------------------------------------------------------

def generate_marketing_plan(profile: dict) -> dict:
    """Create a comprehensive, template-driven marketing plan."""
    btype = profile.get("business_type", "other")
    name = profile.get("name", "your business")
    location = profile.get("location", "your area")
    monthly = profile.get("monthly_budget", 500)
    goals = profile.get("goals", [])
    platforms = profile.get("platforms", ["google", "meta"])
    description = profile.get("description", "")
    bench = INDUSTRY_BENCHMARKS.get(btype, INDUSTRY_BENCHMARKS["other"])
    btype_label = BUSINESS_TYPES.get(btype, {}).get("label", btype)
    btype_emoji = BUSINESS_TYPES.get(btype, {}).get("emoji", "")

    goal_labels = [GOAL_OPTIONS.get(g, g) for g in goals]
    goals_str = ", ".join(goal_labels) if goal_labels else "growing your business"

    summary = (
        f"{btype_emoji} Here's your personalized marketing plan for {name}! "
        f"You're a {btype_label.lower()} in {location} looking to {goals_str.lower()}. "
        f"With a ${monthly}/month budget, we're going to make every dollar count. "
        f"This plan focuses on reaching the right people at the right time, "
        f"starting with quick wins you can do today and building toward a steady stream of "
        f"{goal_labels[0].lower() if goal_labels else 'customers'}."
    )

    plat_recs = PLATFORM_RECOMMENDATIONS.get(btype, PLATFORM_RECOMMENDATIONS["other"])
    budget_info = advise_budget(profile)
    split = budget_info["budget_split"]

    platform_strategy = []
    for plat in platforms:
        rec = next((r for r in plat_recs if r["platform"] == plat), None)
        plat_label = plat.title()
        if plat == "meta":
            plat_label = "Meta (Facebook & Instagram)"
        elif plat == "google":
            plat_label = "Google Ads"

        pct = split.get(plat.title(), split.get(plat_label, "50%"))
        reason = rec["reason"] if rec else f"{plat_label} can help you reach new customers."

        campaign_ideas = _generate_campaign_ideas(profile, plat)

        platform_strategy.append({
            "platform": plat_label,
            "budget_split": pct,
            "strategy": reason,
            "campaign_ideas": campaign_ideas,
        })

    keywords = suggest_keywords(profile)[:10]

    total_clicks_month = max(1, int(monthly / bench["avg_cpc"]))
    total_convs_month = max(1, int(total_clicks_month * bench["avg_conv_rate"] / 100))

    monthly_timeline = (
        f"Month 1: Set up accounts, install tracking, launch your first campaign with "
        f"${bench['suggested_daily_budget_min']}/day. Focus on learning what works. "
        f"Month 2: Review what's performing, pause underperforming ads, increase budget on winners. "
        f"Add retargeting to recapture interested visitors. "
        f"Month 3: Scale what's working to ${monthly / 30:.0f}/day. Launch a second campaign type. "
        f"By now you should have clear data on what resonates with your audience."
    )

    expected_results = (
        f"With ${monthly}/month, you can expect approximately {total_clicks_month} clicks "
        f"and {total_convs_month}\u2013{total_convs_month * 2} {goal_labels[0].lower() if goal_labels else 'conversions'} "
        f"per month based on {btype_label.lower()} industry averages. "
        f"That's about ${monthly / max(total_convs_month, 1):.0f} per "
        f"{'inquiry' if 'inquiries' in goals_str.lower() else 'conversion'}. "
        f"Results improve as platforms learn who your best customers are \u2014 "
        f"give it at least 60\u201390 days before judging."
    )

    quick_wins = [
        "Set up or claim your Google Business Profile \u2014 it's free and shows up in local searches.",
        "Add conversion tracking to your website so you can see what's actually working.",
        f"Make sure your website clearly says what {name} does within the first 5 seconds.",
        "Add high-quality photos to your Google Business Profile and social media.",
        "Ask your happiest customers for Google reviews \u2014 they influence ad performance.",
        f"Create a dedicated landing page for your ads (don't just send people to your homepage).",
    ]
    if btype == "wedding_venue":
        quick_wins.append("Post your venue on The Knot and WeddingWire \u2014 free listings are available.")
    elif btype == "restaurant":
        quick_wins.append("Make sure your menu, hours, and phone number are up to date on Google.")
    elif btype == "vacation_rental":
        quick_wins.append("Respond to every review on your listing platforms \u2014 it boosts visibility.")

    warnings = [
        "Don't expect instant results \u2014 give campaigns 2\u20134 weeks to optimize before changing anything.",
        "Avoid the temptation to pause ads the moment they feel expensive. Early spend is learning investment.",
        "Never set it and forget it \u2014 check your campaigns weekly for the first 3 months.",
        "Be wary of anyone who guarantees specific results. Advertising is testing, not magic.",
    ]

    return {
        "summary": summary,
        "platform_strategy": platform_strategy,
        "keywords": [kw["keyword"] for kw in keywords],
        "monthly_timeline": monthly_timeline,
        "expected_results": expected_results,
        "quick_wins": quick_wins,
        "warnings": warnings,
    }


def _generate_campaign_ideas(profile: dict, platform: str) -> list[str]:
    """Return 2-3 campaign ideas tailored to the profile and platform."""
    btype = profile.get("business_type", "other")
    name = profile.get("name", "your business")
    location = profile.get("location", "your area")
    goals = profile.get("goals", [])

    ideas = []

    if platform == "google":
        ideas.append(
            f"Search Campaign \u2014 Target people actively looking for a "
            f"{BUSINESS_TYPES.get(btype, {}).get('label', 'business').lower()} in {location}."
        )
        if "brand_awareness" in goals or "website_traffic" in goals:
            ideas.append(
                f"Display Campaign \u2014 Show beautiful image ads for {name} on websites "
                f"your potential customers visit."
            )
        ideas.append(
            f"Retargeting Campaign \u2014 Show ads to people who visited your website "
            f"but didn't take action. These are warm leads."
        )
    elif platform == "meta":
        ideas.append(
            f"Instagram Photo/Video Ads \u2014 Showcase {name} with your best visuals. "
            f"Target people in your ideal audience."
        )
        if "more_inquiries" in goals or "more_bookings" in goals:
            ideas.append(
                f"Lead Generation Campaign \u2014 Let people request info without leaving "
                f"Facebook/Instagram. Super easy for them."
            )
        ideas.append(
            f"Lookalike Audience Campaign \u2014 Find new customers who are similar to your "
            f"existing fans and website visitors."
        )
    elif platform == "tiktok":
        ideas.append(
            f"In-Feed Video Ads \u2014 Short, authentic videos that feel native to TikTok. "
            f"Show the personality of {name}."
        )
        ideas.append(
            f"Behind-the-Scenes Content \u2014 Give people a peek behind the curtain. "
            f"Authenticity outperforms polish on TikTok."
        )
    else:
        ideas.append(
            f"Awareness Campaign \u2014 Introduce {name} to new potential customers on {platform.title()}."
        )
        ideas.append(
            f"Engagement Campaign \u2014 Get people interacting with {name} content to build trust."
        )

    return ideas

# ---------------------------------------------------------------------------
# Performance Translator
# ---------------------------------------------------------------------------

def translate_performance(metrics: dict, profile: dict) -> dict:
    """Translate raw ad metrics into plain-English insights."""
    btype = profile.get("business_type", "other")
    name = profile.get("name", "your business")
    bench = INDUSTRY_BENCHMARKS.get(btype, INDUSTRY_BENCHMARKS["other"])
    btype_label = BUSINESS_TYPES.get(btype, {}).get("label", btype)

    clicks = metrics.get("clicks", 0)
    impressions = metrics.get("impressions", 0)
    cost = metrics.get("cost", 0)
    conversions = metrics.get("conversions", 0)
    cpc = metrics.get("cpc", cost / max(clicks, 1))
    ctr = metrics.get("ctr", (clicks / max(impressions, 1)) * 100)
    conv_rate = metrics.get("conv_rate", (conversions / max(clicks, 1)) * 100)
    cpa = cost / max(conversions, 1) if conversions > 0 else None

    goal_word = "leads"
    if profile.get("goals"):
        g = profile["goals"][0]
        goal_word = {
            "more_inquiries": "inquiries",
            "more_bookings": "bookings",
            "website_traffic": "visitors",
            "phone_calls": "calls",
            "online_sales": "sales",
            "local_visits": "visits",
            "brand_awareness": "impressions",
        }.get(g, "leads")

    cpa_comment = ""
    if cpa is not None:
        cpa_comment = f" You spent ${cost:,.0f} \u2014 that's ${cpa:,.0f} per {goal_word[:-1] if goal_word.endswith('s') else goal_word}."
        if btype in ("wedding_venue", "real_estate"):
            cpa_comment += f" For a high-value {btype_label.lower()}, that's likely an incredible return."
        elif cpa < 50:
            cpa_comment += " That's a solid cost per lead."
        elif cpa < 150:
            cpa_comment += " That's reasonable, but let's work on bringing it down."
        else:
            cpa_comment += " That's on the higher side \u2014 we should look at improving your landing page or targeting."

    conv_summary = ""
    if conversions > 0:
        conv_summary = f" and {conversions} of them {_action_verb(profile)}"

    summary = (
        f"This period, {impressions:,} people saw your ad for {name}, "
        f"{clicks:,} were interested enough to click{conv_summary}.{cpa_comment}"
    )

    metrics_explained = []

    visibility_note = "That\u2019s strong visibility!" if impressions > 5000 else "As your campaigns run longer, this will grow."
    metrics_explained.append({
        "label": "People who saw your ad",
        "value": f"{impressions:,}",
        "verdict": "good" if impressions > 1000 else "neutral",
        "explanation": f"{impressions:,} potential customers saw your ad. {visibility_note}",
    })

    ctr_verdict = "good" if ctr >= bench["avg_ctr"] else ("okay" if ctr >= bench["avg_ctr"] * 0.7 else "needs_attention")
    if ctr >= bench["avg_ctr"]:
        ctr_comparison = ", which is above average for " + btype_label.lower() + "s"
        ctr_advice = "Your ad is grabbing attention!"
    else:
        ctr_comparison = ", which is below the " + str(bench["avg_ctr"]) + "% average for " + btype_label.lower() + "s"
        ctr_advice = "Try testing different headlines or images to improve this."
    metrics_explained.append({
        "label": "People who clicked",
        "value": f"{clicks:,}",
        "verdict": ctr_verdict,
        "explanation": f"{clicks:,} people clicked your ad \u2014 that\u2019s a {ctr:.1f}% click rate{ctr_comparison}. {ctr_advice}",
    })

    cpc_verdict = "good" if cpc <= bench["avg_cpc"] else ("okay" if cpc <= bench["avg_cpc"] * 1.3 else "needs_attention")
    cpc_note = "You\u2019re getting a good deal!" if cpc <= bench["avg_cpc"] else "This is a bit high \u2014 improving your Quality Score can help bring it down."
    metrics_explained.append({
        "label": "Cost per click",
        "value": f"${cpc:.2f}",
        "verdict": cpc_verdict,
        "explanation": f"You paid ${cpc:.2f} per click (average for {btype_label.lower()}s is ${bench['avg_cpc']:.2f}). {cpc_note}",
    })

    if conversions > 0:
        conv_verdict = "good" if conv_rate >= bench["avg_conv_rate"] else ("okay" if conv_rate >= bench["avg_conv_rate"] * 0.6 else "needs_attention")
        if conv_rate >= bench["avg_conv_rate"]:
            conv_note = "That\u2019s above average!"
        else:
            conv_note = "The average is " + str(bench["avg_conv_rate"]) + "%. Let\u2019s optimize your landing page to improve this."
        metrics_explained.append({
            "label": f"People who {_action_verb(profile)}",
            "value": str(conversions),
            "verdict": conv_verdict,
            "explanation": f"{conversions} people took action \u2014 that\u2019s a {conv_rate:.1f}% conversion rate. {conv_note}",
        })
    else:
        metrics_explained.append({
            "label": "Conversions",
            "value": "0",
            "verdict": "needs_attention",
            "explanation": (
                "No conversions yet. This is normal in the first 1\u20132 weeks. "
                "Make sure your tracking is set up correctly and your landing page makes it easy to take action."
            ),
        })

    recommendations = _generate_recommendations(metrics, bench, profile)

    return {
        "summary": summary,
        "metrics_explained": metrics_explained,
        "recommendations": recommendations,
    }


def _action_verb(profile: dict) -> str:
    goals = profile.get("goals", [])
    if not goals:
        return "took action"
    mapping = {
        "more_inquiries": "filled out your inquiry form",
        "more_bookings": "made a booking",
        "website_traffic": "visited your site",
        "phone_calls": "called you",
        "online_sales": "made a purchase",
        "local_visits": "got directions to your business",
        "brand_awareness": "engaged with your brand",
        "app_installs": "installed your app",
    }
    return mapping.get(goals[0], "took action")


def _generate_recommendations(metrics: dict, bench: dict, profile: dict) -> list[str]:
    recs = []
    ctr = metrics.get("ctr", 0)
    cpc = metrics.get("cpc", 0)
    conv_rate = metrics.get("conv_rate", 0)
    conversions = metrics.get("conversions", 0)

    if ctr >= bench["avg_ctr"]:
        recs.append("Your click rate is strong \u2014 people like your ad. Keep the current creative running.")
    else:
        recs.append("Your click rate is below average. Try testing new headlines, images, or a stronger call-to-action.")

    if cpc > bench["avg_cpc"] * 1.2:
        recs.append("Your cost per click is higher than average. Check your keyword relevance and Quality Score.")
    elif cpc <= bench["avg_cpc"] * 0.8:
        recs.append("You're getting clicks at a great price. Consider increasing your daily budget to get more of them.")

    if conversions > 0 and conv_rate < bench["avg_conv_rate"]:
        recs.append(
            "People are clicking but not converting. Your landing page might need work \u2014 "
            "make the call-to-action obvious and reduce form fields."
        )
    elif conversions > 0 and conv_rate >= bench["avg_conv_rate"]:
        recs.append("Your conversion rate is solid. Consider expanding your targeting to reach more people like your converters.")

    if conversions == 0:
        recs.append("No conversions yet \u2014 check that your tracking pixel is installed correctly.")
        recs.append("Make sure your landing page loads fast and looks great on mobile phones.")

    if not recs:
        recs.append("Things are looking steady. Keep monitoring weekly and adjust as patterns emerge.")

    return recs

# ---------------------------------------------------------------------------
# Marketing Calendar
# ---------------------------------------------------------------------------

def get_calendar(profile: dict) -> list:
    """Return calendar events relevant to the profile's business type."""
    btype = profile.get("business_type", "other")
    results = []
    for month_data in MARKETING_CALENDAR:
        relevant_events = []
        for event in month_data["events"]:
            if btype in event["types"]:
                your_action = _calendar_action(event, profile)
                relevant_events.append({
                    "name": event["name"],
                    "tip": event["tip"],
                    "your_action": your_action,
                })
        if relevant_events:
            results.append({
                "month": month_data["month"],
                "name": month_data["name"],
                "events": relevant_events,
            })
    return results


def get_upcoming_opportunities(profile: dict) -> list:
    """Return calendar events in the next 60 days relevant to the profile."""
    today = datetime.utcnow()
    current_month = today.month
    next_month = current_month + 1 if current_month < 12 else 1
    third_month = next_month + 1 if next_month < 12 else 1
    target_months = {current_month, next_month, third_month}

    btype = profile.get("business_type", "other")
    results = []
    for month_data in MARKETING_CALENDAR:
        if month_data["month"] in target_months:
            for event in month_data["events"]:
                if btype in event["types"]:
                    results.append({
                        "month": month_data["name"],
                        "name": event["name"],
                        "tip": event["tip"],
                        "your_action": _calendar_action(event, profile),
                        "urgency": "now" if month_data["month"] == current_month else "coming_soon",
                    })
    return results


def _calendar_action(event: dict, profile: dict) -> str:
    name = profile.get("name", "your business")
    btype = profile.get("business_type", "other")
    event_name = event["name"].lower()

    if "wedding" in event_name or "engagement" in event_name:
        return f"Launch a 'Now Booking' campaign for {name}. Feature your best photos and easy inquiry form."
    if "valentine" in event_name:
        return f"Create a romantic experience package for {name}. Run ads starting 2 weeks before."
    if "mother" in event_name or "father" in event_name:
        return f"Promote gift cards and special packages at {name}. Start ads 10 days before."
    if "holiday" in event_name or "christmas" in event_name:
        return f"Run a holiday campaign for {name}. Gift cards and seasonal specials work great."
    if "black friday" in event_name:
        return f"Plan your biggest promotion of the year for {name}. Start teasing it 1 week early."
    if "summer" in event_name or "spring break" in event_name:
        return f"Highlight seasonal offerings at {name}. Run travel-themed ads targeting your key markets."
    if "new year" in event_name or "resolution" in event_name:
        return f"Launch a 'Fresh Start' campaign for {name}. Offer intro deals to attract new customers."
    if "back to school" in event_name:
        return f"Target families getting back to routine. Promote convenience and family-friendly options at {name}."
    if "earth day" in event_name:
        return f"Highlight sustainability efforts at {name}. Share your eco-friendly story on social media."

    return f"Run a timely campaign for {name} tied to this event. Seasonal relevance boosts engagement."

# ---------------------------------------------------------------------------
# Jargon
# ---------------------------------------------------------------------------

def get_jargon_dictionary() -> dict:
    """Return the full jargon dictionary."""
    return JARGON_DICTIONARY


def explain_term(term: str) -> dict | None:
    """Look up a marketing term (case-insensitive). Accepts common variations."""
    key = term.strip().lower().replace("-", "_").replace(" ", "_")
    if key in JARGON_DICTIONARY:
        return {"term": key, **JARGON_DICTIONARY[key]}

    # Fuzzy matching: try partial matches
    for k, v in JARGON_DICTIONARY.items():
        if key in k or key in v["full_name"].lower().replace(" ", "_"):
            return {"term": k, **v}
        if key.replace("_", " ") in v["full_name"].lower():
            return {"term": k, **v}

    return None

# ---------------------------------------------------------------------------
# Ad Copy Generator Helpers
# ---------------------------------------------------------------------------

def generate_ad_copy_prompt(profile: dict, platform: str, campaign_type: str) -> str:
    """Build a detailed prompt for an AI to generate ad copy."""
    name = profile.get("name", "the business")
    btype_label = BUSINESS_TYPES.get(profile.get("business_type", "other"), {}).get("label", "business")
    description = profile.get("description", "")
    location = profile.get("location", "")
    goals = profile.get("goals", [])
    goal_labels = [GOAL_OPTIONS.get(g, g) for g in goals]
    audience = profile.get("target_audience", {})
    website_info = profile.get("website_info", {})

    website_context = ""
    if website_info and not website_info.get("error"):
        title = website_info.get("title", "")
        meta = website_info.get("meta_description", "")
        if title:
            website_context += f"\nWebsite title: {title}"
        if meta:
            website_context += f"\nWebsite meta description: {meta}"

    audience_desc = audience.get("description", "")
    audience_ctx = f"\nTarget audience: {audience_desc}" if audience_desc else ""

    platform_guidelines = {
        "google": (
            "Google Search Ads guidelines:\n"
            "- Up to 15 headlines (max 30 characters each)\n"
            "- Up to 4 descriptions (max 90 characters each)\n"
            "- Include keywords naturally in headlines\n"
            "- Use strong calls-to-action\n"
            "- Include location and unique selling points"
        ),
        "meta": (
            "Meta (Facebook/Instagram) Ads guidelines:\n"
            "- Primary text: 125 characters for best performance\n"
            "- Headline: 40 characters\n"
            "- Description: 30 characters\n"
            "- Emotional, visual language works best\n"
            "- Ask questions or tell stories\n"
            "- Use emojis sparingly but effectively"
        ),
        "tiktok": (
            "TikTok Ads guidelines:\n"
            "- Ad text: 100 characters max\n"
            "- Be casual, authentic, and fun\n"
            "- Avoid sounding like an ad\n"
            "- Use trending language and formats\n"
            "- Focus on the visual story"
        ),
    }

    guidelines = platform_guidelines.get(platform, f"{platform.title()} ad copy guidelines:\n- Be clear and compelling\n- Include a call-to-action")

    prompt = (
        f"Write compelling ad copy for {name}, a {btype_label.lower()} in {location}.\n\n"
        f"Business description: {description}\n"
        f"Goals: {', '.join(goal_labels)}\n"
        f"{audience_ctx}"
        f"{website_context}\n\n"
        f"Campaign type: {campaign_type}\n"
        f"Platform: {platform.title()}\n\n"
        f"{guidelines}\n\n"
        f"Write multiple variations. The tone should be warm, professional, and inviting. "
        f"Highlight what makes {name} unique. "
        f"Make the reader feel excited to take action.\n\n"
        f"Return the copy in this JSON format:\n"
        f'{{"headlines": ["...", "..."], "descriptions": ["...", "..."], "call_to_action": "..."}}'
    )
    return prompt


def generate_placeholder_ad_copy(profile: dict, platform: str) -> dict:
    """Generate template-based ad copy without AI."""
    name = profile.get("name", "Your Business")
    btype = profile.get("business_type", "other")
    location = profile.get("location", "")
    description = profile.get("description", "")
    btype_label = BUSINESS_TYPES.get(btype, {}).get("label", "Business")
    goals = profile.get("goals", [])

    short_name = name if len(name) <= 20 else name[:17] + "..."
    loc_short = location.split(",")[0].strip() if location else ""

    cta_map = {
        "more_inquiries": "Request Info",
        "more_bookings": "Book Now",
        "website_traffic": "Learn More",
        "phone_calls": "Call Now",
        "online_sales": "Shop Now",
        "local_visits": "Get Directions",
        "brand_awareness": "Discover More",
        "app_installs": "Download Now",
    }
    cta = cta_map.get(goals[0], "Learn More") if goals else "Learn More"

    # Extract a compelling detail from the description
    detail = ""
    if description:
        sentences = re.split(r'[.!]', description)
        for s in sentences:
            s = s.strip()
            if len(s) > 15:
                detail = s
                break

    if platform == "google":
        headlines = [
            f"{short_name} | {btype_label}",
            f"{btype_label} in {loc_short}" if loc_short else f"Top-Rated {btype_label}",
            f"Book {short_name} Today",
            f"Award-Winning {btype_label}" if len(f"Award-Winning {btype_label}") <= 30 else f"Stunning {btype_label}",
            f"{cta} \u2014 {short_name}",
        ]
        descriptions = [
            f"Discover {name} in {location}. {detail[:60]}..." if detail else f"Discover {name} in {location}. Unforgettable experiences await.",
            f"Looking for a {btype_label.lower()}? {name} offers something truly special. {cta} today.",
        ]
    elif platform == "meta":
        headlines = [
            f"{name} \u2014 {loc_short}" if loc_short else name,
            f"Your Dream {btype_label}",
            f"Discover {short_name}",
        ]
        descriptions = [
            f"{detail[:120]}. Tap to learn more!" if detail else f"{name} is not your average {btype_label.lower()}. Come see what makes us special.",
            f"Imagine {_imagine_text(btype)}. That's what awaits at {name}. {cta}!",
        ]
    else:
        headlines = [
            name,
            f"{btype_label} in {loc_short}" if loc_short else btype_label,
        ]
        descriptions = [
            f"Discover {name} \u2014 {detail[:80]}" if detail else f"Discover {name} \u2014 a {btype_label.lower()} like no other.",
        ]

    return {
        "headlines": headlines,
        "descriptions": descriptions,
        "call_to_action": cta,
    }


def _imagine_text(btype: str) -> str:
    mapping = {
        "wedding_venue": "saying your vows in a breathtaking setting",
        "vacation_rental": "waking up in paradise on your next getaway",
        "restaurant": "an unforgettable meal with people you love",
        "ecommerce": "finding exactly what you've been looking for",
        "local_service": "having a trusted professional handle everything",
        "real_estate": "walking through the door of your dream home",
        "fitness": "finally feeling strong, confident, and unstoppable",
        "beauty_salon": "walking out feeling like the best version of yourself",
        "photography": "having your most precious moments captured forever",
        "consulting": "having an expert guide you to your next breakthrough",
        "nonprofit": "making a real difference in your community",
    }
    return mapping.get(btype, "an experience that exceeds your expectations")

# ---------------------------------------------------------------------------
# Campaign Builder Helpers
# ---------------------------------------------------------------------------

def build_campaign_config(profile: dict, platform: str, campaign_type: str) -> dict:
    """Build a structured campaign configuration from profile data."""
    name = profile.get("name", "My Business")
    btype = profile.get("business_type", "other")
    location = profile.get("location", "")
    monthly = profile.get("monthly_budget", 500)
    goals = profile.get("goals", [])
    audience = profile.get("target_audience", {})
    bench = INDUSTRY_BENCHMARKS.get(btype, INDUSTRY_BENCHMARKS["other"])
    platforms = profile.get("platforms", ["google", "meta"])
    btype_label = BUSINESS_TYPES.get(btype, {}).get("label", btype)

    platform_count = max(len(platforms), 1)
    daily_budget = round(monthly / 30 / platform_count, 2)
    daily_budget = max(daily_budget, bench["suggested_daily_budget_min"])

    kw_list = suggest_keywords(profile)[:10]
    keywords = [kw["keyword"] for kw in kw_list]
    ad_copy = generate_placeholder_ad_copy(profile, platform)

    type_labels = {
        "search": "Search",
        "display": "Display",
        "video": "Video",
        "shopping": "Shopping",
        "lead_gen": "Lead Generation",
        "awareness": "Brand Awareness",
        "traffic": "Website Traffic",
        "conversions": "Conversions",
    }
    type_label = type_labels.get(campaign_type, campaign_type.replace("_", " ").title())

    campaign_name = f"{name} \u2014 {type_label} Campaign"

    targeting = {
        "locations": audience.get("locations", [location] if location else []),
        "age_range": audience.get("age_range", "18-65"),
        "audience_description": audience.get("description", f"People interested in {btype_label.lower()}s"),
    }

    notes_map = {
        "search": f"This campaign targets people actively searching for {btype_label.lower()}s. It shows text ads on Google Search results when people type relevant keywords.",
        "display": f"This campaign shows image ads for {name} on websites your potential customers visit. Great for building brand awareness.",
        "lead_gen": f"This campaign uses in-app forms to collect contact info from interested people. No website visit needed \u2014 great for reducing friction.",
        "awareness": f"This campaign maximizes the number of people who see {name}. Best for building recognition in {location or 'your area'}.",
        "traffic": f"This campaign drives as many people as possible to your website. Make sure your landing page is ready to convert visitors.",
        "video": f"This campaign shows video ads to your target audience. Even a simple 15-second clip of {name} can be very effective.",
        "conversions": f"This campaign optimizes for people most likely to take action \u2014 fill out a form, make a call, or book. The platform learns and improves over time.",
    }
    notes = notes_map.get(campaign_type, f"This campaign promotes {name} on {platform.title()}.")

    return {
        "platform": platform,
        "campaign_name": campaign_name,
        "campaign_type": campaign_type,
        "daily_budget": daily_budget,
        "keywords": keywords if platform == "google" else [],
        "ad_copy": ad_copy,
        "targeting": targeting,
        "notes": notes,
    }
