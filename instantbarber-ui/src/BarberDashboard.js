import React, { useEffect, useRef, useState } from "react";

function BarberDashboard() {
  const [bookings, setBookings] = useState([]);
  const [message, setMessage] = useState("Waiting for requests...");
  const [soundEnabled, setSoundEnabled] = useState(false);

  // 🔥 NUEVO
  const [barberId, setBarberId] = useState(1);

  const firstComparisonDoneRef = useRef(false);
  const previousBookingIdsRef = useRef([]);
  const audioRef = useRef(null);

  const enableSound = async () => {
    try {
      if (!audioRef.current) {
        setMessage("Audio not loaded.");
        return;
      }

      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      await audioRef.current.play();

      setSoundEnabled(true);
      setMessage("Sound enabled successfully. New bookings will now beep.");
    } catch (error) {
      console.error("Error enabling sound:", error);
      setMessage("Could not enable sound.");
    }
  };

  const playNotificationSound = async () => {
    if (!soundEnabled || !audioRef.current) return false;

    try {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      await audioRef.current.play();
      return true;
    } catch (error) {
      console.error("Error playing notification sound:", error);
      return false;
    }
  };

  const loadBookings = async () => {
    try {
      const response = await fetch(
        `http://localhost:8000/bookings/barber/${barberId}`
      );

      if (!response.ok) {
        throw new Error("Server responded with error");
      }

      const data = await response.json();
      setBookings(data);
    } catch (error) {
      console.error("Error loading bookings:", error);
      setMessage("Error loading requests from backend.");
    }
  };

  const acceptBooking = async (bookingId) => {
    try {
      setMessage(`Accepting booking #${bookingId}...`);

      const response = await fetch(
        `http://localhost:8000/bookings/${bookingId}/accept`,
        {
          method: "PUT",
        }
      );

      if (!response.ok) {
        throw new Error("Failed to accept booking");
      }

      setMessage(`Booking #${bookingId} accepted successfully.`);
      loadBookings();
    } catch (error) {
      console.error("Error accepting booking:", error);
      setMessage(`Error accepting booking #${bookingId}.`);
    }
  };

  useEffect(() => {
    // 🔥 NUEVO: leer barberId dinámico en el futuro
    const savedBarberId = localStorage.getItem("barberId");
    if (savedBarberId) {
      setBarberId(savedBarberId);
    }
  }, []);

  useEffect(() => {
    loadBookings();

    const interval = setInterval(() => {
      loadBookings();
    }, 3000);

    return () => clearInterval(interval);
  }, [barberId]);

  useEffect(() => {
    const currentIds = bookings.map((booking) => booking.id);
    const previousIds = previousBookingIdsRef.current;

    const newIds = currentIds.filter((id) => !previousIds.includes(id));

    if (!firstComparisonDoneRef.current) {
      firstComparisonDoneRef.current = true;
    } else if (newIds.length > 0) {
      playNotificationSound().then((played) => {
        if (played) {
          setMessage(`New booking detected! ID: ${newIds.join(", ")}`);
        } else {
          setMessage(`New booking detected, but sound failed. ID: ${newIds.join(", ")}`);
        }
      });
    } else if (bookings.length === 0) {
      setMessage("No pending requests found.");
    } else {
      setMessage(`Loaded ${bookings.length} pending request(s).`);
    }

    previousBookingIdsRef.current = currentIds;
  }, [bookings]);

  return (
    <>
      <audio ref={audioRef} src="/notification.mp3" preload="auto" controls />

      <div style={{ padding: "40px", fontFamily: "Arial" }}>
        <h1>Barber Dashboard</h1>
        <p>Pending haircut requests will appear here.</p>

        <button
          onClick={loadBookings}
          style={{
            marginTop: "20px",
            marginRight: "10px",
            padding: "12px 20px",
            backgroundColor: "black",
            color: "white",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "16px"
          }}
        >
          LOAD REQUESTS
        </button>

        <button
          onClick={enableSound}
          style={{
            marginTop: "20px",
            padding: "12px 20px",
            backgroundColor: soundEnabled ? "green" : "darkblue",
            color: "white",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "16px"
          }}
        >
          {soundEnabled ? "SOUND ENABLED" : "ENABLE SOUND"}
        </button>

        <p style={{ marginTop: "20px", fontWeight: "bold" }}>{message}</p>

        {bookings.length > 0 && (
          <div style={{ marginTop: "30px" }}>
            <h2>Pending Requests</h2>

            {bookings.map((booking) => (
              <div
                key={booking.id}
                style={{
                  marginBottom: "20px",
                  padding: "15px",
                  border: "1px solid #ccc",
                  borderRadius: "10px",
                  maxWidth: "300px"
                }}
              >
                <strong>Booking #{booking.id}</strong>
                <div>Client ID: {booking.client_id}</div>
                <div>Service ID: {booking.service_id}</div>
                <div>Status: {booking.status}</div>

                <button
                  onClick={() => acceptBooking(booking.id)}
                  style={{
                    marginTop: "12px",
                    padding: "10px 16px",
                    backgroundColor: "green",
                    color: "white",
                    border: "none",
                    borderRadius: "8px",
                    cursor: "pointer",
                    fontSize: "14px"
                  }}
                >
                  ACCEPT
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default BarberDashboard;












