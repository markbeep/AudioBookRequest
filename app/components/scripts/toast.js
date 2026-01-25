const toast = (message, type = "success") => {
  const classNames = {
    success: "success-alert",
    error: "error-alert",
    info: "info-alert",
  };
  Toastify({
    text: message,
    duration: type === "error" ? 10000 : 3000,
    close: true,
    gravity: "top",
    position: "right",
    stopOnFocus: true,
    className: classNames[type],
    style: {
      background: "unset",
    },
  }).showToast();
};
