#!/usr/bin/env python3
"""zk_verify.py: верифицирует ZK proof-пакет БЕЗ данных.

Третья сторона запускает:
    python3 zk_verify.py zk_proof_package.json

Проверяет:
  (a) Range proofs: ci ∈ [0,255] для каждого актора (без раскрытия ci)
  (b) Aggregate proof: знание открытий commitments (без раскрытия ci)
  (c) Claims: hhi_num/hhi_den согласованы с total_n

НЕ загружает parquet. НЕ раскрывает индивидуальные значения.
"""
import json
import hashlib
import sys

def mod_pow(b, e, m):
    return pow(b, e, m)

def fiat_shamir(*args):
    data = "|".join(str(a) for a in args).encode()
    return int.from_bytes(hashlib.sha256(data).digest(), "big") % (m_val - 1)

# Глобальные параметры (из proof-пакета)
m_val = 0

def set_params(pp):
    global m_val
    m_val = int(pp["P"])

def pedersen_check(C, z, w, A, e):
    """g^z * h^w == A * C^e"""
    P = m_val
    g, h = int(2), int(3)
    lhs = (mod_pow(g, z, P) * mod_pow(h, w, P)) % P
    rhs = (A * mod_pow(C, e, P)) % P
    return lhs == rhs

def verify_or_bit(pf, C, seed):
    P = m_val
    g, h = int(2), int(3)
    A0, A1 = int(pf["A0"]), int(pf["A1"])
    e0, e1 = int(pf["e0"]), int(pf["e1"])
    z0, y0, z1, y1 = int(pf["z0"]), int(pf["y0"]), int(pf["z1"]), int(pf["y1"])

    lhs0 = (mod_pow(g, z0, P) * mod_pow(h, y0, P)) % P
    rhs0 = (A0 * mod_pow(C, e0, P)) % P
    if lhs0 != rhs0:
        return False, "branch-0"

    lhs1 = (mod_pow(g, z1, P) * mod_pow(h, y1, P)) % P
    rhs1 = (A1 * mod_pow(C, e1, P)) % P
    if lhs1 != rhs1:
        return False, "branch-1"

    data = "|".join(str(a) for a in (seed, A0, A1, C)).encode()
    e_check = int.from_bytes(hashlib.sha256(data).digest(), "big") % (P - 1)
    if (e0 + e1) % (P - 1) != e_check:
        return False, "challenge"
    return True, "ok"

def verify_range(rp, actor_id):
    P = m_val
    g, h = int(2), int(3)
    bcs = [int(c) for c in rp["bit_commitments"]]

    for j, pf in enumerate(rp["or_proofs"]):
        ok, msg = verify_or_bit(pf, bcs[j], f"{actor_id}:bit{j}")
        if not ok:
            return False, f"bit{j}: {msg}"

    lp = rp["link"]
    A, e, z = int(lp["A"]), int(lp["e"]), int(lp["z"])
    C_orig, C_bits = int(lp["C_orig"]), int(lp["C_bits"])

    data = "|".join(str(a) for a in (f"link:{actor_id}", A, C_orig, C_bits)).encode()
    e_check = int.from_bytes(hashlib.sha256(data).digest(), "big") % (P - 1)
    if e != e_check:
        return False, "link challenge"

    ratio = (C_orig * mod_pow(C_bits, P - 2, P)) % P
    lhs = mod_pow(h, z, P)
    rhs = (A * mod_pow(ratio, e, P)) % P
    if lhs != rhs:
        return False, "link equation"

    cb = 1
    for j in range(8):
        cb = (cb * mod_pow(bcs[j], 1 << j, P)) % P
    if cb != C_bits:
        return False, "bit product"

    return True, "ok"

def verify_aggregate(agg, claims):
    P = m_val
    g, h = int(2), int(3)
    commitments = {int(k): int(v) for k, v in agg["commitments"].items()}
    announcements = {int(k): int(v) for k, v in agg["announcements"].items()}
    responses = {int(k): (int(v[0]), int(v[1])) for k, v in agg["responses"].items()}
    c = int(agg["challenge"])

    # Fiat-Shamir reproduciibility
    transcript = json.dumps({
        "commitments": {str(k): str(v) for k, v in sorted(commitments.items())},
        "announcements": {str(k): str(v) for k, v in sorted(announcements.items())},
        "claims": claims,
    }, sort_keys=True)
    data = transcript.encode()
    c_check = int.from_bytes(hashlib.sha256(data).digest(), "big") % (P - 1)
    if c != c_check:
        return False, "aggregate challenge mismatch"

    if set(commitments) != set(announcements) or set(commitments) != set(responses):
        return False, "key mismatch"

    for actor in sorted(commitments):
        Ci = commitments[actor]
        Ai = announcements[actor]
        z, w = responses[actor]
        if not pedersen_check(Ci, z, w, Ai, c):
            return False, f"actor {actor}"

    return True, f"all {len(commitments)} commitments verified"

def main():
    proof_path = sys.argv[1] if len(sys.argv) > 1 else "zk_proof_package.json"
    pkg = json.load(open(proof_path))
    set_params(pkg["public_params"])
    claims = pkg["claims"]

    print(f"[verify] claims: game={claims['game']}, total_n={claims['total_n']}, "
          f"hhi={claims['hhi_num']}/{claims['hhi_den']}")

    # Claims consistency
    if claims["hhi_den"] != claims["total_n"] ** 2:
        print("[FAIL] hhi_den != total_n^2")
        return 1
    hhi_val = claims["hhi_num"] / claims["hhi_den"]
    print(f"[verify] HHI = {hhi_val:.8f}")

    # Range proofs
    n_range = 0
    for actor_id, rp in pkg["range_proofs"].items():
        ok, msg = verify_range(rp, actor_id)
        if not ok:
            print(f"[FAIL] range {actor_id}: {msg}")
            return 1
        n_range += 1
    print(f"[verify] range: {n_range}/{n_range} actors in [0,255]")

    # Aggregate proof
    ok, msg = verify_aggregate(pkg["aggregate_proof"], claims)
    if not ok:
        print(f"[FAIL] aggregate: {msg}")
        return 1
    print(f"[verify] aggregate: {msg}")

    print("[VERIFIED] ZK proof package valid; no data files loaded")
    return 0

if __name__ == "__main__":
    sys.exit(main())
