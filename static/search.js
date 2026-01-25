const onSearch = () => {
    const search_term = document.querySelector("input").value;
    document.getElementById("search").disabled = true;
    document.getElementById("search-text").style.display = "none";
    document.getElementById("search-spinner").style.display = "inline-block";
    window.location.href = `/search?q=${encodeURIComponent(search_term)}`;
  };
  const onPageChange = page => {
    const url = new URL(window.location);
    url.searchParams.set("page", page);
    window.location = url;
  };
