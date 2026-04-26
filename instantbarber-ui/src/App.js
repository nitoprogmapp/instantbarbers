import React, { useState, useEffect } from "react";
import ClientDashboard from "./ClientDashboard";
import ClientBookingStatus from "./ClientBookingStatus";
import WelcomeScreen from "./screens/WelcomeScreen";
import RegisterChoiceScreen from "./screens/RegisterChoiceScreen";
import LoginChoiceScreen from "./screens/LoginChoiceScreen";
import CustomerRegisterScreen from "./screens/CustomerRegisterScreen";

function App() {
  const [screen, setScreen] = useState("welcome");
  const [bookingId, setBookingId] = useState(null);

  useEffect(() => {
    const savedId = localStorage.getItem("bookingId");
    if (savedId) {
      setBookingId(savedId);
    }
  }, []);

  if (screen === "welcome") {
    return (
      <WelcomeScreen
        onRegisterClick={() => setScreen("registerChoice")}
        onLoginClick={() => setScreen("loginChoice")}
      />
    );
  }

  if (screen === "registerChoice") {
    return (
      <RegisterChoiceScreen
        onBarberRegisterClick={() => alert("Barber register screen next")}
        onCustomerRegisterClick={() => setScreen("customerRegister")}
      />
    );
  }

  if (screen === "loginChoice") {
    return (
      <LoginChoiceScreen
        onBarberLoginClick={() => alert("Barber login screen next")}
        onCustomerLoginClick={() => setScreen("client")}
      />
    );
  }

  if (screen === "customerRegister") {
    return <CustomerRegisterScreen />;
  }

  if (screen === "client") {
    if (bookingId) {
      return <ClientBookingStatus />;
    }
    return <ClientDashboard />;
  }

  return null;
}

export default App;