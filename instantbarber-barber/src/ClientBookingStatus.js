import React, { useEffect, useState } from "react";

function ClientBookingStatus() {
  const [booking, setBooking] = useState(null);
  const [message, setMessage] = useState("Loading...");
  const [secondsLeft, setSecondsLeft] = useState(30);
  const [paymentEnabled, setPaymentEnabled] = useState(false);
  const [completeEnabled, setCompleteEnabled] = useState(false);
  const [bookingId, setBookingId] = useState(null);

  // 🔥 Obtener bookingId real
  useEffect(() => {
    const savedId = localStorage.getItem("bookingId");
    if (savedId) {
      setBookingId(savedId);
    }
  }, []);

  const updateUI = (data) => {
    setBooking(data);

    if (data.status === "pending") {
      setMessage("Waiting for barber to accept...");
      setPaymentEnabled(false);
      setCompleteEnabled(false);
    }

    if (data.status === "accepted") {
      setMessage("Barber accepted. Please pay now.");
      setPaymentEnabled(true);
      setCompleteEnabled(false);
    }

    if (data.status === "paid") {
      setMessage("Go to the barber and press COMPLETE after.");
      setPaymentEnabled(false);
      setCompleteEnabled(true);
    }

    if (data.status === "completed") {
      setMessage("Haircut completed.");
      setPaymentEnabled(false);
      setCompleteEnabled(false);
    }

    if (data.status === "expired") {
      setMessage("Time expired. Please create a new booking.");
      setPaymentEnabled(false);
      setCompleteEnabled(false);
    }

    if (data.status === "cancelled") {
      setMessage("Booking cancelled.");
      setPaymentEnabled(false);
      setCompleteEnabled(false);
    }
  };

  const loadBookingStatus = async () => {
    if (!bookingId) return;

    try {
      const response = await fetch(
        `http://localhost:8000/bookings/${bookingId}`
      );

      if (!response.ok) throw new Error();

      const data = await response.json();
      updateUI(data);
    } catch {
      setMessage("Error loading booking status.");
    }
  };

  // 🔥 PAY NOW CORREGIDO (FUERZA ACTUALIZACIÓN)
  const payNow = async () => {
    try {
      const response = await fetch(
        `http://localhost:8000/bookings/${bookingId}/paid`,
        {
          method: "PUT",
        }
      );

      if (!response.ok) {
        throw new Error("Payment failed");
      }

      // 🔥 FORZAR REFRESH REAL DEL ESTADO
      await loadBookingStatus();

    } catch (error) {
      console.error(error);
      setMessage("Error processing payment.");
    }
  };

  // 🔥 COMPLETE CORREGIDO
  const markComplete = async () => {
    try {
      const response = await fetch(
        `http://localhost:8000/bookings/${bookingId}/complete`,
        {
          method: "PUT",
        }
      );

      if (!response.ok) {
        throw new Error("Complete failed");
      }

      await loadBookingStatus();

    } catch (error) {
      console.error(error);
      setMessage("Error completing haircut.");
    }
  };

  // 🔥 polling
  useEffect(() => {
    loadBookingStatus();

    const interval = setInterval(loadBookingStatus, 3000);
    return () => clearInterval(interval);
  }, [bookingId]);

  // 🔥 countdown
  useEffect(() => {
    let interval;

    if (paymentEnabled && secondsLeft > 0) {
      interval = setInterval(() => {
        setSecondsLeft((prev) => prev - 1);
      }, 1000);
    }

    if (!paymentEnabled) {
      setSecondsLeft(30);
    }

    return () => clearInterval(interval);
  }, [paymentEnabled, secondsLeft]);

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>Client Booking Status</h1>

      <p>{message}</p>

      {booking && (
        <div>
          <p>Booking #{booking.id}</p>
          <p>Status: {booking.status}</p>
        </div>
      )}

      {paymentEnabled && (
        <>
          <p>Time left: {secondsLeft}s</p>
          <button onClick={payNow}>PAY NOW</button>
        </>
      )}

      {completeEnabled && (
        <button onClick={markComplete}>COMPLETE</button>
      )}
    </div>
  );
}

export default ClientBookingStatus;






