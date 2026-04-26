import stripe

# 🔐 CLAVE TEMPORAL (NO REAL)
stripe.api_key = "sk_test_TEMPORAL"


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
