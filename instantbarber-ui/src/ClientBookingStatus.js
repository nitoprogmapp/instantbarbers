import React, { useCallback, useEffect, useRef, useState } from "react";

function ClientBookingStatus() {
  const [booking, setBooking] = useState(null);
  const [message, setMessage] = useState("Loading...");
  const [secondsLeft, setSecondsLeft] = useState(30);
  const [paymentEnabled, setPaymentEnabled] = useState(false);
  const [completeEnabled, setCompleteEnabled] = useState(false);
  const [bookingId, setBookingId] = useState(null);
  const [isPaying, setIsPaying] = useState(false);
  const [isRedirecting, setIsRedirecting] = useState(false);

  const pollingRef = useRef(null);
  const countdownRef = useRef(null);

  useEffect(() => {
    const savedId = localStorage.getItem("bookingId");
    if (savedId) {
      setBookingId(savedId);
    } else {
      setMessage("No active booking found.");
    }
  }, []);

  const stopCountdown = useCallback(() => {
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const clearActiveBookingAndReturn = useCallback(
    (finalMessage) => {
      stopCountdown();
      stopPolling();
      setPaymentEnabled(false);
      setCompleteEnabled(false);
      setIsPaying(false);
      setIsRedirecting(true);
      setSecondsLeft(30);
      setMessage(finalMessage);

      localStorage.removeItem("bookingId");
      setBookingId(null);
      setBooking(null);

      setTimeout(() => {
        window.location.reload();
      }, 1200);
    },
    [stopCountdown, stopPolling]
  );

  const updateUI = useCallback(
    (data) => {
      setBooking(data);

      if (data.status === "pending") {
        setMessage("Waiting for barber to accept...");
        setPaymentEnabled(false);
        setCompleteEnabled(false);
        setIsPaying(false);
        setSecondsLeft(30);
        stopCountdown();
        return;
      }

      if (data.status === "accepted") {
        if (!isPaying) {
          setMessage("Barber accepted. Please pay now.");
          setPaymentEnabled(true);
          setCompleteEnabled(false);
        }
        return;
      }

      if (data.status === "paid") {
        setMessage("Payment successful. Go to the barber and press COMPLETE after.");
        setPaymentEnabled(false);
        setCompleteEnabled(true);
        setIsPaying(false);
        setSecondsLeft(30);
        stopCountdown();
        return;
      }

      if (data.status === "completed") {
        clearActiveBookingAndReturn("Haircut completed. Returning...");
        return;
      }

      if (data.status === "expired") {
        clearActiveBookingAndReturn("Time expired. Returning...");
        return;
      }

      if (data.status === "cancelled") {
        clearActiveBookingAndReturn("Booking cancelled. Returning...");
      }
    },
    [clearActiveBookingAndReturn, isPaying, stopCountdown]
  );

  const loadBookingStatus = useCallback(async () => {
    if (!bookingId || isRedirecting) return;

    try {
      const response = await fetch(`http://127.0.0.1:8000/bookings/${bookingId}`);

      if (!response.ok) {
        throw new Error("Could not load booking");
      }

      const data = await response.json();
      updateUI(data);
    } catch (error) {
      console.error("Error loading booking status:", error);
      setMessage("Error loading booking status.");
    }
  }, [bookingId, isRedirecting, updateUI]);

  const payNow = useCallback(async () => {
    if (!bookingId || isPaying || isRedirecting) return;

    try {
      setIsPaying(true);
      setPaymentEnabled(false);
      setMessage("Processing payment...");
      stopCountdown();

      const response = await fetch(
        `http://127.0.0.1:8000/bookings/${bookingId}/paid`,
        {
          method: "PUT",
          headers: {
            accept: "application/json",
          },
        }
      );

      if (!response.ok) {
        let errorMessage = "Payment failed.";
        try {
          const errorData = await response.json();
          if (errorData?.detail) {
            errorMessage = errorData.detail;
          }
        } catch (_) {}
        throw new Error(errorMessage);
      }

      // 🔥 Delay clave para que backend actualice
      await new Promise((resolve) => setTimeout(resolve, 500));

      await loadBookingStatus();

    } catch (error) {
      console.error("Error processing payment:", error);
      setMessage(error.message || "Error processing payment.");
      setIsPaying(false);
      await loadBookingStatus();
    }
  }, [bookingId, isPaying, isRedirecting, loadBookingStatus, stopCountdown]);

  const markComplete = useCallback(async () => {
    if (!bookingId || isRedirecting) return;

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/bookings/${bookingId}/complete`,
        {
          method: "PUT",
          headers: {
            accept: "application/json",
          },
        }
      );

      if (!response.ok) {
        let errorMessage = "Complete failed.";
        try {
          const errorData = await response.json();
          if (errorData?.detail) {
            errorMessage = errorData.detail;
          }
        } catch (_) {}
        throw new Error(errorMessage);
      }

      await loadBookingStatus();
    } catch (error) {
      console.error("Error completing haircut:", error);
      setMessage(error.message || "Error completing haircut.");
    }
  }, [bookingId, isRedirecting, loadBookingStatus]);

  useEffect(() => {
    if (!bookingId || isRedirecting) return;

    loadBookingStatus();

    pollingRef.current = setInterval(() => {
      loadBookingStatus();
    }, 2000);

    return () => {
      stopPolling();
    };
  }, [bookingId, isRedirecting, loadBookingStatus, stopPolling]);

  useEffect(() => {
    stopCountdown();

    if (
      paymentEnabled &&
      !isPaying &&
      !isRedirecting &&
      booking?.status === "accepted" &&
      secondsLeft > 0
    ) {
      countdownRef.current = setInterval(() => {
        setSecondsLeft((prev) => {
          if (prev <= 1) {
            stopCountdown();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }

    return () => {
      stopCountdown();
    };
  }, [paymentEnabled, isPaying, isRedirecting, booking?.status, secondsLeft, stopCountdown]);

  useEffect(() => {
    if (booking?.status === "accepted" && secondsLeft === 0 && !isPaying && !isRedirecting) {
      setMessage("Time expired. Waiting for backend confirmation...");
      setPaymentEnabled(false);
    }
  }, [secondsLeft, booking?.status, isPaying, isRedirecting]);

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>Client Booking Status</h1>

      <p>{message}</p>

      {booking && (
        <div style={{ marginTop: "20px" }}>
          <p>Booking #{booking.id}</p>
          <p>Status: {booking.status}</p>
        </div>
      )}

      {paymentEnabled && (
        <div style={{ marginTop: "20px" }}>
          <p>Time left: {secondsLeft}s</p>
          <button onClick={payNow} disabled={isPaying}>
            {isPaying ? "PROCESSING..." : "PAY NOW"}
          </button>
        </div>
      )}

      {completeEnabled && (
        <div style={{ marginTop: "20px" }}>
          <button onClick={markComplete}>COMPLETE</button>
        </div>
      )}
    </div>
  );
}

export default ClientBookingStatus;










