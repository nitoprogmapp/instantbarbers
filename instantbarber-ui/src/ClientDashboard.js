import React, { useEffect, useState } from "react";

function ClientDashboard() {
  const [barbers, setBarbers] = useState([]);
  const [message, setMessage] = useState("");
  const [loadingBooking, setLoadingBooking] = useState(false);

  const clientId = 2;

  useEffect(() => {
    fetch("http://localhost:8000/barbers")
      .then((res) => res.json())
      .then((data) => setBarbers(data))
      .catch((error) => {
        console.error("Error loading barbers:", error);
        setMessage("Error loading barbers");
      });
  }, []);

  const createBooking = async (barberId) => {
    if (loadingBooking) return;

    try {
      setLoadingBooking(true);
      setMessage(`Creating booking for barber ${barberId}...`);

      const response = await fetch(
        `http://localhost:8000/bookings?client_id=${clientId}&barber_id=${barberId}&service_id=1`,
        {
          method: "POST",
        }
      );

      if (!response.ok) {
        throw new Error("Failed to create booking");
      }

      const data = await response.json();

      localStorage.setItem("bookingId", data.id);
      setMessage(`Booking created successfully. ID: ${data.id}`);
    } catch (error) {
      console.error("Error creating booking:", error);
      setMessage("Error creating booking");
    } finally {
      setLoadingBooking(false);
    }
  };

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>View Barbers</h1>

      {message && <p style={{ fontWeight: "bold" }}>{message}</p>}

      {barbers.map((barber) => (
        <div
          key={barber.id}
          style={{
            marginBottom: "20px",
            padding: "15px",
            border: "1px solid #ccc",
            borderRadius: "10px",
            maxWidth: "300px",
          }}
        >
          <h3>{barber.name}</h3>

          <button
            onClick={() => createBooking(barber.id)}
            disabled={loadingBooking}
          >
            {loadingBooking ? "CREATING..." : "GET BARBER"}
          </button>
        </div>
      ))}
    </div>
  );
}

export default ClientDashboard;


