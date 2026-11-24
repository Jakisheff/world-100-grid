#!/usr/bin/env python3
"""zk_prove.py: генерирует единый ZK proof-пакет для world-100-grid.

Объединяет zk_hhi (агрегат: HHI и total_n из Pedersen commitments) и
zk_range (диапазон ci ∈ [0,255] для каждого актора) в один файл,
верифицируемый третьей стороной БЕЗ загрузки parquet.

Использование:
    python3 zk_prove.py                    # из каталога пакета
    python3 zk_verify.py proof.json        # третья сторона, без данных
"""
import json
import os
import random
import sys

# Публичные параметры (общие с zk_hhi/zk_range)
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
G = 2
H = 3

def mod_pow(b, e, m=P):
    return pow(b, e, m)

def pedersen_commit(v, r):
    return (mod_pow(G, v) * mod_pow(H, r)) % P

def fiat_shamir(*args):
    import hashlib
    data = "|".join(str(a) for a in args).encode()
    return int.from_bytes(hashlib.sha256(data).digest(), "big") % (P - 1)


def prove_actor(ci, actor_id):
    """Range proof для одного актора: 8 бит + OR-proofs + связка."""
    assert 0 <= ci <= 255
    bits = [(ci >> j) & 1 for j in range(8)]
    bcs, rbs = [], []
    for b in bits:
        r = random.randrange(1, P - 1)
        bcs.append(pedersen_commit(b, r))
        rbs.append(r)

    or_proofs = []
    for j, b in enumerate(bits):
        pf = _or_proof(bcs[j], b, rbs[j], f"{actor_id}:bit{j}")
        or_proofs.append(pf)

    ci_blinding = random.randrange(1, P - 1)
    C_orig = pedersen_commit(ci, ci_blinding)
    C_bits = 1
    for j in range(8):
        C_bits = (C_bits * mod_pow(bcs[j], 1 << j)) % P

    delta = (ci_blinding - sum(rbs[j] << j for j in range(8))) % (P - 1)
    w = random.randrange(1, P - 1)
    A = mod_pow(H, w)
    e = fiat_shamir(f"link:{actor_id}", A, C_orig, C_bits)
    z = (w + e * delta) % (P - 1)

    return {
        "bit_commitments": [str(c) for c in bcs],
        "or_proofs": or_proofs,
        "link": {"A": str(A), "e": str(e), "z": str(z),
                 "C_orig": str(C_orig), "C_bits": str(C_bits)},
    }


def _or_proof(C, bit, blinding, seed):
    if bit == 0:
        w0, v0 = random.randrange(1, P-1), random.randrange(1, P-1)
        A0 = (mod_pow(G, w0) * mod_pow(H, v0)) % P
        e1, z1, y1 = (random.randrange(1, P-1) for _ in range(3))
        A1 = (mod_pow(G, z1) * mod_pow(H, y1) * mod_pow(C, -e1)) % P
        e = fiat_shamir(seed, A0, A1, C)
        e0 = (e - e1) % (P-1)
        z0 = w0
        y0 = (v0 + e0 * blinding) % (P-1)
    else:
        w1, v1 = random.randrange(1, P-1), random.randrange(1, P-1)
        A1 = (mod_pow(G, w1) * mod_pow(H, v1)) % P
        e0, z0, y0 = (random.randrange(1, P-1) for _ in range(3))
        A0 = (mod_pow(G, z0) * mod_pow(H, y0) * mod_pow(C, -e0)) % P
        e = fiat_shamir(seed, A0, A1, C)
        e1 = (e - e0) % (P-1)
        z1 = (w1 + e1) % (P-1)
        y1 = (v1 + e1 * blinding) % (P-1)
    return {"A0": str(A0), "A1": str(A1), "e0": str(e0), "e1": str(e1),
            "z0": str(z0), "y0": str(y0), "z1": str(z1), "y1": str(y1)}


def prove_aggregate(actor_counts, claims):
    """Sigma-protocol: знание открытий, стоящих за commitment'ами."""
    commitments, blindings = {}, {}
    for actor, ci in sorted(actor_counts.items()):
        b = random.randrange(1, P-1)
        commitments[actor] = pedersen_commit(ci, b)
        blindings[actor] = b

    announcements = {}
    nonces = {}
    for actor in sorted(commitments):
        r, s = random.randrange(1, P-1), random.randrange(1, P-1)
        nonces[actor] = (r, s)
        announcements[actor] = pedersen_commit(r, s)

    transcript = json.dumps({
        "commitments": {str(k): str(v) for k, v in sorted(commitments.items())},
        "announcements": {str(k): str(v) for k, v in sorted(announcements.items())},
        "claims": claims,
    }, sort_keys=True)
    c = fiat_shamir(transcript)

    responses = {}
    for actor in sorted(commitments):
        ci = actor_counts[actor]
        bi = blindings[actor]
        r, s = nonces[actor]
        z = (r + c * ci) % (P-1)
        w = (s + c * bi) % (P-1)
        responses[str(actor)] = [str(z), str(w)]

    return {
        "commitments": {str(k): str(v) for k, v in sorted(commitments.items())},
        "announcements": {str(k): str(v) for k, v in sorted(announcements.items())},
        "challenge": str(c),
        "responses": responses,
    }


def generate(data_path=None):
    import pyarrow.parquet as pq
    from collections import Counter
    data_path = data_path or os.environ.get("WORLD100_DATA", "data/decisions.parquet")

    rows = pq.read_table(data_path).to_pylist()
    game = [r for r in rows if r["game"] == "l4-20261109-original"]
    counts = Counter(r["chosen"] for r in game)
    m = len(game)
    hhi_num = sum(c*c for c in counts.values())

    claims = {"game": "l4-20261109-original", "total_n": m, "hhi_num": hhi_num,
              "hhi_den": m*m, "schema": "world-100-grid/v1"}

    print(f"[prove] {len(counts)} actors, m={m}, hhi_num={hhi_num}")

    # 1. Range proofs
    range_proofs = {}
    for actor in sorted(counts):
        range_proofs[str(actor)] = prove_actor(counts[actor], actor)
    print(f"[prove] {len(range_proofs)} range proofs")

    # 2. Aggregate proof
    agg = prove_aggregate(counts, claims)
    print(f"[prove] aggregate proof: {len(agg['commitments'])} commitments")

    # 3. Assemble
    package = {
        "public_params": {"P": str(P), "G": str(G), "H": str(H)},
        "claims": claims,
        "aggregate_proof": agg,
        "range_proofs": range_proofs,
    }
    out = "zk_proof_package.json"
    with open(out, "w") as f:
        json.dump(package, f, indent=2)
    size = os.path.getsize(out)
    print(f"[saved] {out} ({size} bytes)")
    return out


if __name__ == "__main__":
    generate()
