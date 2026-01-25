/**
 * @param {string|null} [theme]
 */
const setTheme = theme => {
  if (!theme) {
    theme = localStorage.getItem("theme");
    if (!theme) {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "night"
        : "nord";
    }
  }
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("theme", theme);
  if (theme === "night") {
    for (const elem of document.getElementsByClassName("light-dark-toggle")) {
      elem.classList.add("DARKCLASS");
      document.documentElement.classList.add("dark");
    }
  } else {
    for (const elem of document.getElementsByClassName("light-dark-toggle")) {
      elem.classList.remove("DARKCLASS");
      document.documentElement.classList.remove("dark");
    }
  }
};
const toggleTheme = () => {
  const theme = document.documentElement.getAttribute("data-theme");

  const newTheme = theme === "nord" ? "night" : "nord";
  setTheme(newTheme);
};
document.addEventListener("DOMContentLoaded", () => {
  setTheme();
});
