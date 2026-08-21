import os

import stripe


# Clave secreta configurada en las variables de entorno de Render.
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY no está configurada.")


def create_payment_intent(amount, currency, barber_stripe_account, app_fee):

    intent = stripe.PaymentIntent.create(
        amount=int(amount * 100),
        currency=currency,
        payment_method_types=["card"],
        application_fee_amount=app_fee,
        transfer_data={
            "destination": barber_stripe_account
        }
    )

    return intent
