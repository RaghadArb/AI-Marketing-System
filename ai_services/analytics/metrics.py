#this file is to do the equations and calculations on campaign performance data 

def calculate_ctr(
    views,
    clicks
):

    if views == 0:
        return 0

    return round(
        (clicks / views) * 100,
        2
    )


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