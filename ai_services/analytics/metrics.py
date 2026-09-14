#this file is to do the equations and calculations on campaign performance data 

def calculate_ctr(
    views,
    clicks
):

    if not views:
        return 0

    return round(
        (clicks / views) * 100,
        2
    )


def calculate_aggregate_ctr(clicks, denominator):
    if not denominator:
        return None
    try:
        clicks_value = float(clicks or 0)
        denom_value = float(denominator)
    except (TypeError, ValueError):
        return None
    if denom_value <= 0:
        return None
    return round((clicks_value / denom_value) * 100, 2)


def calculate_engagement_rate(
    views,
    likes,
    comments,
    shares
):

    if views == 0:
        return 0

    engagement = (
        likes +
        comments +
        shares
    )

    return round(
        (engagement / views) * 100,
        2
    )


def calculate_total_engagement(
    likes,
    comments,
    shares
):

    return (
        likes +
        comments +
        shares
    )