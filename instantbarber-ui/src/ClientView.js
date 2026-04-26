import React, { useEffect, useState } from "react";
import ClientBookingStatus from "./ClientBookingStatus";

function ClientView() {
  const [barbers, setBarbers] = useState([]);
  const [message, setMessage] = useState("");
  const [bookingCreated, setBookingCreated] = useState(false);

  const clientId = 2;

  useEffect(() => {
    fetch("http://localhost:8000/barbers")
      .then((res) => res.json())
      .then((data) => setBarbers(data))
      .catch(() => setMessage("Error loading barbers"));

    // 🔥 NUEVO: revisa si ya hay booking
    const savedId = localStorage.getItem("bookingId");
    if (savedId) {
      setBookingCreated(true);
    }
  }, []);

  const createBooking = (barberId) => {
    fetch(
      `http://localhost:8000/bookings?client_id=${clientId}&barber_id=${barberId}&service_id=2`,
      {
        method: "POST",
      }
    )
      .then((res) => res.json())
      .then((data) => {
        setMessage(`Booking creado con ID: ${data.id}`);

        localStorage.setItem("bookingId", data.id);

        setBookingCreated(true); // 🔥 clave
      })
      .catch(() => setMessage("Error creando booking"));
  };

  if (bookingCreated) {
    return <ClientBookingStatus />;
  }

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>Choose your barber</h1>

      {message && <p>{message}</p>}

      {barbers.map((barber) => (
        <div key={barber.id}>
          <h3>{barber.name}</h3>

          <button onClick={() => createBooking(barber.id)}>
            GET BARBER
          </button>
        </div>
      ))}
    </div>
  );
}

export default ClientView;


