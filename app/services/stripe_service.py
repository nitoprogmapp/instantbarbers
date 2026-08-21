import os

import stripe


stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY no está configurada.")


def create_payment_intent(amount, currency, barber_stripe_account, app_fee):

    intent = stripe.PaymentIntent.create(
        amount=int(amount * 100),
        currency=currency,
        payment_method_types=["card"],
        application_fee_amount=app_fee,
        stripe_account=barber_stripe_account
    )

    return intent