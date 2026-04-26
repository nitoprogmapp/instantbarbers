import React from "react";

function LoginChoiceScreen({ onBarberLoginClick, onCustomerLoginClick }) {
  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Login</h1>

      <div style={styles.buttonColumn}>
        <button style={styles.primaryButton} onClick={onBarberLoginClick}>
          Login as Barber
        </button>

        <button style={styles.secondaryButton} onClick={onCustomerLoginClick}>
          Login as Customer
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
  title: {
    fontSize: "32px",
    marginBottom: "30px",
  },
  buttonColumn: {
    display: "flex",
    flexDirection: "column",
    gap: "20px",
  },
  primaryButton: {
    padding: "14px 24px",
    fontSize: "16px",
    backgroundColor: "#111",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    minWidth: "240px",
  },
  secondaryButton: {
    padding: "14px 24px",
    fontSize: "16px",
    backgroundColor: "#fff",
    color: "#111",
    border: "1px solid #111",
    borderRadius: "8px",
    cursor: "pointer",
    minWidth: "240px",
  },
};

export default LoginChoiceScreen;
