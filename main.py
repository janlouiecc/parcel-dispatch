"""Start the Parcel Dispatch development server with ``python main.py``."""


def main() -> None:
    import uvicorn

    uvicorn.run("delivery.main:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
