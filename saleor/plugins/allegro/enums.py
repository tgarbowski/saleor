import enum


class AllegroErrors(enum.Enum):
    ALLEGRO_ERROR = 'allegro_error'
    NO_OFFERS_FOUND = 'no_offers_found'
    BID_OR_PURCHASED = 'bid_or_purchased'
    TASK_FAILED = 'task_failed'
    NO_OFFER_NEEDS_ENDING = 'no_offer_needs_ending'
