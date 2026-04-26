import React from "react";
import logo from "../assets/images/instantbarber-logo.png";

function WelcomeScreen({ onRegisterClick, onLoginClick }) {
  return (
    <div style={styles.container}>
      <img
        src={logo}
        alt="InstantBarber Logo"
        style={styles.logo}
      />

      <h1 style={styles.title}>Welcome to InstantBarber</h1>

      <div style={styles.buttonRow}>
        <button style={styles.primaryButton} onClick={onRegisterClick}>
          Register
        </button>

        <button style={styles.secondaryButton} onClick={onLoginClick}>
          Login
        </button>
      </div>
    </div>
  );
}

const styles = {
  container: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#f5f5f5",
  },
  logo: {
    width: "220px",
    marginBottom: "20px",
  },
  title: {
    fontSize: "36px",
    marginBottom: "30px",
  },
  buttonRow: {
    display: "flex",
    gap: "20px",
  },
  primaryButton: {
    padding: "12px 24px",
    fontSize: "16px",
    backgroundColor: "#111",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
  },
  secondaryButton: {
    padding: "12px 24px",
    fontSize: "16px",
    backgroundColor: "#fff",
    color: "#111",
    border: "1px solid #111",
    borderRadius: "8px",
    cursor: "pointer",
  },
};

export default WelcomeScreen;
