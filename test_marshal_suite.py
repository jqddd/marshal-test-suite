"""
Test suite for Python's marshal module.

The suite checks byte-level determinism, round-trip correctness,
boundary values, negative inputs, cyclic/shared references, protocol
differences, and deterministic fuzzing.

It is designed for the software testing assignment on marshal stability.
"""

import hashlib
import math
import marshal
import os
import random
import subprocess
import sys
import textwrap
import unittest


MARSHAL_FORMAT_VERSION = 4


class TestMarshalStability(unittest.TestCase):
    """Tests for marshal stability and correctness."""

    def assert_stable_dump(self, value, version=MARSHAL_FORMAT_VERSION):
        """Assert that repeated dumps of the same value are byte-identical."""
        dumped_once = marshal.dumps(value, version)
        dumped_twice = marshal.dumps(value, version)
        self.assertEqual(
            dumped_once,
            dumped_twice,
            "The same input must produce the same byte stream.",
        )
        return dumped_once

    def assert_round_trip_equal(self, value, version=MARSHAL_FORMAT_VERSION):
        """Assert byte determinism and round-trip logical correctness."""
        dumped = self.assert_stable_dump(value, version)
        loaded = marshal.loads(dumped)
        self.assertEqual(value, loaded)
        return loaded

    # ------------------------------------------------------------------
    # 1. Deterministic baseline: equivalence partitioning
    # ------------------------------------------------------------------

    def test_primitive_determinism_and_correctness(self):
        """
        Black-box testing: equivalence partitioning.

        Covers primitive supported values and verifies:
        1. repeated serialization is byte-identical;
        2. deserialization reconstructs an equivalent object.
        """
        values = [
            None,
            True,
            False,
            1024,
            -1024,
            "A standard string",
            b"A byte string",
        ]

        for value in values:
            with self.subTest(value=repr(value)):
                self.assert_round_trip_equal(value)

    def test_collection_determinism_and_correctness(self):
        """
        Black-box testing: equivalence partitioning.

        Covers supported collection types and nested structures.
        """
        values = [
            [],
            (),
            {},
            set(),
            frozenset(),
            [1, 2, 3],
            (1, "a", b"b"),
            {"key": [1, 2, 3], "value": "CrossPlatformTestData"},
            {"nested": [{"x": (1, 2)}, {"y": b"bytes"}]},
            {"set": {1, 2, 3}, "frozen": frozenset({"a", "b"})},
        ]

        for value in values:
            with self.subTest(value=repr(value)):
                self.assert_round_trip_equal(value)

    # ------------------------------------------------------------------
    # 2. Boundary value analysis
    # ------------------------------------------------------------------

    def test_integer_boundary_values(self):
        """
        Black-box testing: boundary value analysis.

        Covers zero, sign boundaries, 32-bit/64-bit boundaries,
        and integers larger than machine-word size.
        """
        values = [
            0,
            -1,
            1,
            2**31 - 1,
            2**31,
            -(2**31),
            2**63 - 1,
            2**63,
            -(2**63),
            2**128,
            -(2**128),
        ]

        for value in values:
            with self.subTest(value=value):
                self.assert_round_trip_equal(value)

    def test_unicode_and_bytes_boundaries(self):
        """
        Black-box testing: boundary value analysis.

        Covers empty, short, Unicode, emoji, Chinese text, and
        large strings/bytes.
        """
        string_values = [
            "",
            "a",
            "ASCII text",
            "中文字符串",
            "emoji🙂test",
            "a" * 100_000,
        ]
        bytes_values = [
            b"",
            b"a",
            bytes(range(256)),
            b"x" * 100_000,
        ]

        for value in string_values + bytes_values:
            with self.subTest(type=type(value).__name__, length=len(value)):
                self.assert_round_trip_equal(value)

    def test_collection_boundaries(self):
        """
        Black-box testing: boundary value analysis.

        Covers empty, single-element, and large collections.
        """
        values = [
            [],
            [1],
            list(range(100_000)),
            {},
            {"only": 1},
            {str(i): i for i in range(1_000)},
            (),
            (1,),
            tuple(range(10_000)),
        ]

        for value in values:
            with self.subTest(type=type(value).__name__):
                self.assert_round_trip_equal(value)

    def test_floating_point_special_values(self):
        """
        Black-box testing: boundary value analysis.

        Covers IEEE-754 special values. NaN requires special checking
        because NaN is not equal to itself.
        """
        finite_values = [
            0.0,
            1.0,
            -1.0,
            sys.float_info.min,
            sys.float_info.max,
            float("inf"),
            float("-inf"),
        ]

        for value in finite_values:
            with self.subTest(value=value):
                self.assert_round_trip_equal(value)

        negative_zero = -0.0
        loaded_negative_zero = marshal.loads(
            self.assert_stable_dump(negative_zero)
        )
        self.assertEqual(math.copysign(1.0, loaded_negative_zero), -1.0)

        nan_value = float("nan")
        loaded_nan = marshal.loads(self.assert_stable_dump(nan_value))
        self.assertTrue(math.isnan(loaded_nan))

        self.assertEqual(
            marshal.dumps(float("nan"), MARSHAL_FORMAT_VERSION),
            marshal.dumps(float("nan"), MARSHAL_FORMAT_VERSION),
        )

    def test_complex_number_round_trip(self):
        """Black-box testing: complex-number correctness and determinism."""
        values = [
            0j,
            1 + 2j,
            -3.5 + 4.25j,
            complex(float("inf"), -0.0),
        ]

        for value in values:
            with self.subTest(value=value):
                loaded = self.assert_round_trip_equal(value)
                if value.imag == 0.0:
                    self.assertEqual(
                        math.copysign(1.0, loaded.imag),
                        math.copysign(1.0, value.imag),
                    )

    def test_extreme_deep_nesting_is_rejected_safely(self):
        """
        Black-box testing: robustness boundary.

        Deeply nested objects should raise a Python exception instead
        of crashing the interpreter.
        """
        deep_object = None
        for _ in range(5_000):
            deep_object = [deep_object]

        with self.assertRaises(ValueError) as context:
            marshal.dumps(deep_object, MARSHAL_FORMAT_VERSION)

        self.assertIn("object too deeply nested", str(context.exception))

    # ------------------------------------------------------------------
    # 3. White-box inspired tests: reference tracking and protocols
    # ------------------------------------------------------------------

    def test_cyclic_structures_supported_in_protocol_v3_plus(self):
        """
        White-box inspired testing.

        Protocol v3+ uses reference tracking, so cyclic objects can be
        serialized and their topology should be preserved.
        """
        cyclic_list = []
        cyclic_list.append(cyclic_list)

        dumped = marshal.dumps(cyclic_list, 3)
        loaded = marshal.loads(dumped)

        self.assertIs(loaded[0], loaded)

    def test_protocol_version_degradation_for_cycles(self):
        """
        White-box inspired testing.

        Older marshal protocol versions do not support cyclic reference
        tracking, while protocol v3+ does.
        """
        cyclic_list = []
        cyclic_list.append(cyclic_list)

        with self.assertRaises(ValueError):
            marshal.dumps(cyclic_list, 0)

        dumped_v3 = marshal.dumps(cyclic_list, 3)
        loaded_v3 = marshal.loads(dumped_v3)

        self.assertIs(loaded_v3[0], loaded_v3)

    def test_shared_reference_identity_is_preserved(self):
        """
        White-box inspired testing.

        Checks whether non-cyclic shared references are reconstructed as
        shared objects after unmarshalling.
        """
        shared_dict = {"secret": 42}
        original = [shared_dict, shared_dict]

        loaded = marshal.loads(marshal.dumps(original, 3))

        self.assertIs(loaded[0], loaded[1])
        self.assertEqual(loaded[0], {"secret": 42})

    def test_code_object_same_runtime_determinism_is_recorded(self):
        """
        White-box inspired testing for internal type support.

        Code objects are internal CPython objects. Their byte streams are
        expected to vary across Python versions, but repeated dumps inside
        the same runtime should still be deterministic.
        """
        def sample_function(value):
            return value + 1

        code_object = sample_function.__code__
        dumped_once = marshal.dumps(code_object, MARSHAL_FORMAT_VERSION)
        dumped_twice = marshal.dumps(code_object, MARSHAL_FORMAT_VERSION)

        self.assertEqual(dumped_once, dumped_twice)

        current_hash = hashlib.sha256(dumped_once).hexdigest()
        print(
            "\n[CI-LOG] Code object observation: "
            f"platform={sys.platform}, "
            f"python={sys.version_info.major}.{sys.version_info.minor}, "
            f"marshal_version={marshal.version}, "
            f"sha256={current_hash}"
        )

    # ------------------------------------------------------------------
    # 4. Negative testing and malformed input fuzzing
    # ------------------------------------------------------------------

    def test_unmarshallable_object_rejection(self):
        """
        Black-box testing: negative testing.

        User-defined custom objects are not supported by marshal and
        should be rejected safely.
        """
        class CustomClass:
            pass

        with self.assertRaises(ValueError) as context:
            marshal.dumps(CustomClass(), MARSHAL_FORMAT_VERSION)

        self.assertIn("unmarshallable object", str(context.exception))

    def test_malformed_bytes_are_rejected_safely(self):
        """
        Black-box testing: malformed input robustness.

        Invalid byte streams should raise Python exceptions instead of
        crashing the interpreter.
        """
        malformed_streams = [
            b"x\x00\x00\x00\x00",
            b"s\xff\xff\xff\xffbad_data",
            b"(",
            b"\xda" * 100,
        ]

        expected_exceptions = (ValueError, EOFError, TypeError)

        for stream in malformed_streams:
            with self.subTest(stream=stream):
                with self.assertRaises(expected_exceptions):
                    marshal.loads(stream)

    # ------------------------------------------------------------------
    # 5. Cross-process / cross-OS stability experiments
    # ------------------------------------------------------------------

    def test_cross_os_primitive_hash_is_stable_for_version_4(self):
        """
        Cross-OS determinism test.

        This test uses an explicit marshal format version to avoid
        accidental changes caused by future default-version changes.
        """
        standard_data = {
            "key": [1, 2, 3],
            "value": "CrossPlatformTestData",
        }

        dumped = marshal.dumps(standard_data, MARSHAL_FORMAT_VERSION)
        current_hash = hashlib.sha256(dumped).hexdigest()

        print(
            "\n[CI-LOG] Primitive observation: "
            f"platform={sys.platform}, "
            f"python={sys.version_info.major}.{sys.version_info.minor}, "
            f"sha256={current_hash}"
        )

        expected_hash = (
            "357b5c0366cc35181791b658305fdb7c43de23b15d1eac0"
            "bc73b3131d9a73bd5"
        )
        self.assertEqual(current_hash, expected_hash)

    def test_set_serialization_behavior_across_hash_seeds(self):
        """
        Cross-process exploratory test for unordered collections.

        This test does not require set serialization to be stable across
        different PYTHONHASHSEED values, because set iteration order may depend
        on hash randomization. Instead, it checks that serialization is
        repeatable when the hash seed is fixed, and records whether different
        seeds produce different byte streams.
        """
        sub_code = """
import hashlib
import marshal

test_set = {"alpha", "bravo", "charlie", "delta", "echo", "foxtrot"}
dumped = marshal.dumps(test_set, 4)
print(hashlib.sha256(dumped).hexdigest(), end="")
"""

        seeds = ["0", "1", "2", "3", "42", "123"]
        hashes_by_seed = {}

        for seed in seeds:
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = seed

            first = subprocess.run(
                [sys.executable, "-c", sub_code],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            ).stdout.strip()

            second = subprocess.run(
                [sys.executable, "-c", sub_code],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            ).stdout.strip()

            self.assertEqual(
                first,
                second,
                f"Set serialization was not repeatable with PYTHONHASHSEED={seed}.",
            )

            hashes_by_seed[seed] = first

        unique_hashes = set(hashes_by_seed.values())

        print(f"\n[CI-LOG] Set hashes by PYTHONHASHSEED: {hashes_by_seed}")
        print(f"[CI-LOG] Unique set hashes: {len(unique_hashes)}")

        if len(unique_hashes) > 1:
            print(
                "[CI-LOG] Observation: set serialization changed across "
                "different hash seeds."
            )
        else:
            print(
                "[CI-LOG] Observation: set serialization remained stable across "
                "the tested hash seeds."
            )

    # ------------------------------------------------------------------
    # 6. Deterministic random fuzzing
    # ------------------------------------------------------------------

    def make_random_marshal_object(self, rng, depth=0):
        """
        Generate a deterministic random marshal-compatible object.

        This is a lightweight property-based fuzzing substitute that uses
        only the Python standard library.
        """
        if depth >= 4:
            terminal_values = [
                None,
                True,
                False,
                rng.randint(-(2**32), 2**32),
                rng.uniform(-1_000_000.0, 1_000_000.0),
                "".join(rng.choice("abcXYZ中文🙂") for _ in range(5)),
                bytes(rng.randint(0, 255) for _ in range(5)),
            ]
            return rng.choice(terminal_values)

        choice = rng.choice(
            [
                "none",
                "bool",
                "int",
                "float",
                "str",
                "bytes",
                "list",
                "tuple",
                "dict",
            ]
        )

        if choice == "none":
            return None
        if choice == "bool":
            return rng.choice([True, False])
        if choice == "int":
            return rng.randint(-(2**80), 2**80)
        if choice == "float":
            return rng.uniform(-1_000_000.0, 1_000_000.0)
        if choice == "str":
            length = rng.randint(0, 20)
            return "".join(rng.choice("abcXYZ中文🙂") for _ in range(length))
        if choice == "bytes":
            length = rng.randint(0, 20)
            return bytes(rng.randint(0, 255) for _ in range(length))
        if choice == "list":
            return [
                self.make_random_marshal_object(rng, depth + 1)
                for _ in range(rng.randint(0, 5))
            ]
        if choice == "tuple":
            return tuple(
                self.make_random_marshal_object(rng, depth + 1)
                for _ in range(rng.randint(0, 5))
            )

        size = rng.randint(0, 5)
        return {
            f"k{i}_{rng.randint(0, 999)}": self.make_random_marshal_object(
                rng,
                depth + 1,
            )
            for i in range(size)
        }

    def test_deterministic_random_fuzzing(self):
        """
        Black-box testing: deterministic fuzzing.

        Randomly generates supported nested objects and checks the core
        properties of marshal:
        1. repeated dumps are byte-identical;
        2. loads(dumps(x)) is equal to x.
        """
        rng = random.Random(12345)

        for index in range(200):
            value = self.make_random_marshal_object(rng)
            with self.subTest(index=index, value=repr(value)[:80]):
                self.assert_round_trip_equal(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
