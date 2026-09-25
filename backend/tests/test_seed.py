from app import seed


def test_seed_is_idempotent(client, capsys):
    seed.main()
    seed.main()
    output = capsys.readouterr().out
    assert "Created test account" in output
    assert "already exists" in output
    response = client.post(
        "/api/auth/login", json={"username": seed.USERNAME, "password": seed.PASSWORD}
    )
    assert response.status_code == 200
    user = response.json()["user"]
    assert (user["username"], user["firstName"], user["lastName"]) == ("nyugrader", "NYU", "Grader")
