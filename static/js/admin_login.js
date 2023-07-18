document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("login-form");
  const passwordInput = document.getElementById("password");

  form.addEventListener("submit", function (event) {
    event.preventDefault();

    // Get the password value from the input field
    const password = passwordInput.value;

    // Compute the SHA-256 hash of the password using the SubtleCrypto API
    crypto.subtle.digest("SHA-256", new TextEncoder().encode(password))
      .then(hashBuffer => {
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(byte => byte.toString(16).padStart(2, "0")).join("");

        // Set the computed hash as the value of the password field
        passwordInput.value = hashHex;

        // Submit the form with the hashed password
        form.submit();
      })
      .catch(error => {
        console.error("Error computing SHA-256 hash:", error);
      });
  });
});