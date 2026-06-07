"""
Python `marshal` 模块测试套件

本脚本用于测试 Python 内部模块 `marshal` 的稳定性、正确性及输出确定性。
结合了黑盒测试（等价类划分、边界值分析）与白盒测试（内部逻辑覆盖）。
"""

import marshal
import unittest
import hashlib  # 修复跨环境测试缺失的哈希库
import sys      # 修复跨环境测试缺失的系统状态库


class TestMarshalStability(unittest.TestCase):
    """测试 `marshal` 模块的核心类。"""

    def test_primitive_determinism(self):
        """
        黑盒测试 - 等价类划分 (EP):
        确保基本数据类型的序列化完全一致且输出稳定。
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
                    "基本数据类型必须产生哈希一致的字节流。"
                )

    def test_integer_boundary_values(self):
        """
        黑盒测试 - 边界值分析 (BVA):
        测试底层 C 语言处理整数时的最大/最小内存边界。
        """
        boundaries = [
            0,
            -1,
            1,
            2**31 - 1,   # 32位最大值
            -2**31,      # 32位最小值
            2**63 - 1,   # 64位最大值
            -2**63,      # 64位最小值
            2**128       # 触发大整数 (BigInt) 处理逻辑的极大值
        ]
        for val in boundaries:
            with self.subTest(val=val):
                dumped = marshal.dumps(val)
                loaded = marshal.loads(dumped)
                self.assertEqual(
                    val, loaded,
                    f"整数 {val} 在序列化/反序列化后数据丢失或错误。"
                )

    def test_floating_point_anomalies(self):
        """
        黑盒测试 - 边界值分析 (BVA):
        测试 IEEE 754 标准下的极端浮点数值 (无穷大与 NaN)。
        """
        # Inf 和 -Inf 应当是稳定的
        self.assertEqual(
            marshal.dumps(float('inf')),
            marshal.dumps(float('inf')),
            "正无穷大序列化结果不一致。"
        )
        self.assertEqual(
            marshal.dumps(float('-inf')),
            marshal.dumps(float('-inf')),
            "负无穷大序列化结果不一致。"
        )

        # NaN 的底层二进制等价性测试
        nan1 = float('nan')
        nan2 = float('nan')
        self.assertEqual(
            marshal.dumps(nan1),
            marshal.dumps(nan2),
            "相同环境下的 NaN 应当产生相同的底层字节流。"
        )

    def test_cyclic_structures_support(self):
        """
        白盒测试 - 内部逻辑覆盖:
        修正了之前的错误认知。在协议版本 3 及以上，
        marshal 已通过底层 FLAG_REF 机制支持循环引用。
        测试其是否能成功序列化并反序列化带有循环引用的列表。
        """
        cyclic_list = []
        cyclic_list.append(cyclic_list)

        # 现代版本应当成功序列化并保留引用关系 (修正：底层 C 函数不支持关键字参数)
        dumped = marshal.dumps(cyclic_list, 3)
        loaded = marshal.loads(dumped)
        
        self.assertIs(loaded[0], loaded, "反序列化后的循环引用关系应当被正确保留。")

    def test_unmarshallable_object_rejection(self):
        """
        黑盒测试 - 异常处理:
        专门测试自定义类等真正无法序列化的对象，
        确保模块正确拦截并抛出 ValueError。
        """
        class CustomClass:
            pass
            
        with self.assertRaises(ValueError) as context:
            marshal.dumps(CustomClass())
            
        self.assertIn("unmarshallable object", str(context.exception))

    def test_collection_boundaries(self):
        """
        黑盒测试 - 边界值分析 (BVA):
        测试极小的集合 (空) 与极大的集合 (触发内存分页)。
        """
        empty_dict = {}
        empty_list = []
        empty_tuple = ()

        # 校验空集合
        self.assertEqual(empty_dict, marshal.loads(marshal.dumps(empty_dict)))
        self.assertEqual(empty_list, marshal.loads(marshal.dumps(empty_list)))
        self.assertEqual(empty_tuple, marshal.loads(marshal.dumps(empty_tuple)))

        # 校验大容量集合（10万条数据）
        large_list = list(range(100_000))
        self.assertEqual(large_list, marshal.loads(marshal.dumps(large_list)))

    def test_set_determinism_warning(self):
        """
        白盒测试 - 底层机制交互:
        测试 C 语言序列化器与 Python 哈希随机化 (PYTHONHASHSEED) 之间的交互。
        确保在单一运行周期内，集合序列化保持确定性。
        """
        test_set = {1, 2, "a", "b", 3.14}
        dump1 = marshal.dumps(test_set)
        dump2 = marshal.dumps(test_set)

        self.assertEqual(
            dump1, dump2,
            "同一进程生命周期内，集合的序列化必须保持稳定。"
        )

    def test_cross_os_determinism(self):
        """
        Cross-OS and Cross-Version Determinism Test.
        Ensures that marshal.dumps() outputs identical byte streams 
        across different operating systems for the same Python version.
        """
        # 1. Define standard test data (Changed to pure English to prevent any encoding side-effects)
        standard_data = {"key": [1, 2, 3], "value": "CrossPlatformTestData"}
        
        # 2. Generate bytes and calculate SHA-256 hash
        dumped_bytes = marshal.dumps(standard_data)
        current_hash = hashlib.sha256(dumped_bytes).hexdigest()
        
        # 3. Print environment details (Pure English to prevent Windows UnicodeEncodeError)
        print(f"\n[CI-LOG] OS: {sys.platform}, Python: {sys.version_info.major}.{sys.version_info.minor}")
        print(f"[CI-LOG] Generated Hash: {current_hash}")
        
        # Solidified golden hashes verified by CI matrix
        expected_hashes = {
            (3, 9): "b47c5a4083698de57ab76ef9d211557d89584e5eeeffb86a57e39a6ed8edf994",
            (3, 10): "b47c5a4083698de57ab76ef9d211557d89584e5eeeffb86a57e39a6ed8edf994",
            (3, 11): "b47c5a4083698de57ab76ef9d211557d89584e5eeeffb86a57e39a6ed8edf994",
            (3, 12): "b47c5a4083698de57ab76ef9d211557d89584e5eeeffb86a57e39a6ed8edf994",
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