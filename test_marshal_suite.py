"""
Python `marshal` Module Test Suite

This script tests the stability, correctness, and output determinism 
of the internal `marshal` module using both black-box and white-box methods.
"""

import marshal
import unittest
import hashlib
import sys


class TestMarshalStability(unittest.TestCase):
    """Test core stability features of the marshal module."""

    def test_primitive_determinism(self):
        """
        Black-box - Equivalence Partitioning (EP):
        Ensures primitive types produce identical deterministic byte streams.
        """
        data = [
            1024,
            -1024,
            "A standard string",
            b"A byte string",
            True,
            False,
            None
        ]
        for item in data:
            with self.subTest(item=item):
                dump1 = marshal.dumps(item)
                dump2 = marshal.dumps(item)
                self.assertEqual(
                    dump1, dump2,
                    "Primitive types must produce identical byte streams."
                )

    def test_integer_boundary_values(self):
        """
        Black-box - Boundary Value Analysis (BVA):
        Tests memory boundaries for integer handling in the underlying C layer.
        """
        boundaries = [
            0,
            -1,
            1,
            2**31 - 1,   # 32-bit Max
            -2**31,      # 32-bit Min
            2**63 - 1,   # 64-bit Max
            -2**63,      # 64-bit Min
            2**128       # BigInt triggering point
        ]
        for val in boundaries:
            with self.subTest(val=val):
                dumped = marshal.dumps(val)
                loaded = marshal.loads(dumped)
                self.assertEqual(
                    val, loaded,
                    f"Data loss or corruption detected for integer: {val}"
                )

    def test_floating_point_anomalies(self):
        """
        Black-box - Boundary Value Analysis (BVA):
        Tests IEEE 754 extreme floating-point values (Infinities and NaN).
        """
        self.assertEqual(
            marshal.dumps(float('inf')),
            marshal.dumps(float('inf')),
            "Positive infinity serialization is non-deterministic."
        )
        self.assertEqual(
            marshal.dumps(float('-inf')),
            marshal.dumps(float('-inf')),
            "Negative infinity serialization is non-deterministic."
        )

        nan1 = float('nan')
        nan2 = float('nan')
        self.assertEqual(
            marshal.dumps(nan1),
            marshal.dumps(nan2),
            "NaN must produce identical underlying byte streams in the same environment."
        )

    def test_cyclic_structures_support(self):
        """
        White-box - Internal Logic Coverage:
        Verifies that marshal supports cyclic references correctly in protocol v3+.
        """
        cyclic_list = []
        cyclic_list.append(cyclic_list)

        dumped = marshal.dumps(cyclic_list, 3)
        loaded = marshal.loads(dumped)
        
        self.assertIs(loaded[0], loaded, "Cyclic reference topology must be preserved.")

    def test_unmarshallable_object_rejection(self):
        """
        Black-box - Exception Handling:
        Ensures custom classes are safely rejected with a ValueError.
        """
        class CustomClass:
            pass
            
        with self.assertRaises(ValueError) as context:
            marshal.dumps(CustomClass())
            
        self.assertIn("unmarshallable object", str(context.exception))

    def test_collection_boundaries(self):
        """
        Black-box - Boundary Value Analysis (BVA):
        Tests empty collections and large-scale data capacities.
        """
        empty_dict = {}
        empty_list = []
        empty_tuple = ()

        self.assertEqual(empty_dict, marshal.loads(marshal.dumps(empty_dict)))
        self.assertEqual(empty_list, marshal.loads(marshal.dumps(empty_list)))
        self.assertEqual(empty_tuple, marshal.loads(marshal.dumps(empty_tuple)))

        large_list = list(range(100_000))
        self.assertEqual(large_list, marshal.loads(marshal.dumps(large_list)))

    def test_set_determinism_warning(self):
        """
        White-box - Underlying Mechanism Interaction:
        Verifies serialization stability within a single process lifecycle.
        """
        test_set = {1, 2, "a", "b", 3.14}
        dump1 = marshal.dumps(test_set)
        dump2 = marshal.dumps(test_set)

        self.assertEqual(
            dump1, dump2,
            "Set serialization must remain stable within the same process lifecycle."
        )

    def test_cross_os_determinism(self):
        """
        Cross-OS and Cross-Version Determinism Test.
        Ensures that marshal.dumps() outputs identical byte streams 
        across different operating systems for the same Python version.
        """
        standard_data = {"key": [1, 2, 3], "value": "CrossPlatformTestData"}
        
        dumped_bytes = marshal.dumps(standard_data)
        current_hash = hashlib.sha256(dumped_bytes).hexdigest()
        
        print(f"\n[CI-LOG] OS: {sys.platform}, Python: {sys.version_info.major}.{sys.version_info.minor}")
        print(f"[CI-LOG] Generated Hash: {current_hash}")
        
        expected_hashes = {
            (3, 9): "357b5c0366cc35181791b658305fdb7c43de23b15d1eac0bc73b3131d9a73bd5",
            (3, 10): "357b5c0366cc35181791b658305fdb7c43de23b15d1eac0bc73b3131d9a73bd5",
            (3, 11): "357b5c0366cc35181791b658305fdb7c43de23b15d1eac0bc73b3131d9a73bd5",
            (3, 12): "357b5c0366cc35181791b658305fdb7c43de23b15d1eac0bc73b3131d9a73bd5",
        }
        
        version_tuple = (sys.version_info.major, sys.version_info.minor)
        if version_tuple in expected_hashes:
            self.assertEqual(
                current_hash, 
                expected_hashes[version_tuple],
                f"Mismatch detected on {sys.platform} for Python {version_tuple}."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)