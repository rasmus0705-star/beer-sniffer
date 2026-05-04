from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Beer, PriceHistory, PriceAlert

router = APIRouter()


@router.get("/beers-with-prices")
def get_beers(db: Session = Depends(get_db)):
    beers = db.query(Beer).options(joinedload(Beer.prices)).all()

    result = []

    for beer in beers:
        if not beer.prices:
            continue

        sorted_prices = sorted(beer.prices, key=lambda p: p.price_dkk)
        cheapest = sorted_prices[0]

        result.append({
            "id": beer.id,
            "name": beer.name,
            "image": beer.image,
            "cheapest_price": cheapest.price_dkk,
            "shop": cheapest.shop_name,
            "discount_pct": cheapest.discount_pct or 0,
            "prices": [
                {
                    "shop": p.shop_name,
                    "price": p.price_dkk,
                    "url": p.url,
                    "discount_pct": p.discount_pct,
                }
                for p in sorted_prices
            ]
        })

    return result


# 🔥 UI MED ALT
@router.get("/ui", response_class=HTMLResponse)
def ui():
    return """
    <html>
    <head>
        <title>BeerSniffer</title>
        <style>
            body {
                font-family: Arial;
                background: #f5f5f5;
                padding: 20px;
            }

            .filters {
                margin-bottom: 15px;
            }

            input, select {
                padding: 8px;
                margin-right: 10px;
            }

            .top {
                margin-bottom: 20px;
            }

            .top h2 {
                margin-bottom: 10px;
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                gap: 20px;
            }

            .card {
                position: relative;
                background: white;
                border-radius: 12px;
                padding: 15px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.1);
            }

            .badge {
                position: absolute;
                top: 10px;
                left: 10px;
                background: red;
                color: white;
                padding: 5px 8px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
            }

            .top-card {
                border: 2px solid gold;
            }

            img {
                width: 100%;
                height: 180px;
                object-fit: cover;
                border-radius: 8px;
                background: #eee;
            }

            .price {
                font-size: 18px;
                font-weight: bold;
            }

            button {
                margin-top: 6px;
                width: 100%;
                padding: 8px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }

            .buy { background: #2ecc71; color: white; }
            .alert { background: #f39c12; color: white; }
        </style>
    </head>

    <body>

        <h1>🍺 BeerSniffer</h1>

        <div class="filters">
            <input id="search" placeholder="Søg..." oninput="applyFilters()" />
            <input id="maxPrice" type="number" placeholder="Max pris" oninput="applyFilters()" />

            <select id="sort" onchange="applyFilters()">
                <option value="default">Sortering</option>
                <option value="discount">Bedste tilbud</option>
                <option value="price">Billigste først</option>
            </select>

            <label>
                <input type="checkbox" id="onlyDeals" onchange="applyFilters()" />
                Kun tilbud
            </label>
        </div>

        <div class="top">
            <h2>🔥 Top 10 deals</h2>
            <div class="grid" id="top"></div>
        </div>

        <div class="grid" id="grid"></div>

        <script>
        let allBeers = [];

        function render(list, elementId, highlightTop=false) {
            const grid = document.getElementById(elementId);
            grid.innerHTML = "";

            list.forEach(beer => {

                const card = document.createElement("div");
                card.className = "card";

                if (highlightTop) {
                    card.classList.add("top-card");
                }

                card.innerHTML = `
                    ${beer.discount_pct ? `<div class="badge">-${beer.discount_pct}%</div>` : ""}

                    <img src="${beer.image || 'https://via.placeholder.com/200'}" />

                    <h3>${beer.name}</h3>

                    <div class="price">${beer.cheapest_price} kr</div>
                    <div>${beer.shop}</div>

                    <button class="buy" onclick="window.open('${beer.prices[0].url}')">
                        Køb
                    </button>

                    <button class="alert" onclick="createAlert(${beer.id})">
                        🔔 Alert
                    </button>
                `;

                grid.appendChild(card);
            });
        }

        function applyFilters() {
            let filtered = [...allBeers];

            const search = document.getElementById("search").value.toLowerCase();
            const maxPrice = document.getElementById("maxPrice").value;
            const onlyDeals = document.getElementById("onlyDeals").checked;
            const sort = document.getElementById("sort").value;

            if (search) {
                filtered = filtered.filter(b => b.name.toLowerCase().includes(search));
            }

            if (maxPrice) {
                filtered = filtered.filter(b => b.cheapest_price <= maxPrice);
            }

            if (onlyDeals) {
                filtered = filtered.filter(b => b.discount_pct > 0);
            }

            if (sort === "discount") {
                filtered.sort((a, b) => b.discount_pct - a.discount_pct);
            }

            if (sort === "price") {
                filtered.sort((a, b) => a.cheapest_price - b.cheapest_price);
            }

            render(filtered, "grid");

            const topDeals = [...allBeers]
                .filter(b => b.discount_pct > 0)
                .sort((a, b) => b.discount_pct - a.discount_pct)
                .slice(0, 10);

            render(topDeals, "top", true);
        }

        fetch("/beers-with-prices")
            .then(res => res.json())
            .then(data => {
                allBeers = data;
                applyFilters();
            });

        function createAlert(id) {
            const price = prompt("Notify me under price:");

            fetch(`/alerts?beer_id=${id}&target_price=${price}&email=test@test.dk`, {
                method: "POST"
            })
            .then(() => alert("Alert oprettet!"));
        }
        </script>

    </body>
    </html>
    """