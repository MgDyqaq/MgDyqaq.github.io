#!/usr/bin/env python3
"""
A+B Problem 评测脚本
支持: AC, WA, TLE, RE, MLE, CE
"""

import subprocess
import resource
import time
import os
import sys
import json
import shutil
from pathlib import Path
from typing import Tuple, Dict, Any

# ============================================
# 配置
# ============================================
TIME_LIMIT = 1.0  # 秒
MEMORY_LIMIT = 512 * 1024 * 1024  # 512MB（字节）

# 路径配置
BASE_DIR = Path(__file__).parent
TESTCASE_DIR = BASE_DIR / "testcases"
SOURCE_FILE = BASE_DIR / "solution.cpp"
EXEC_FILE = Path("/tmp/solution")  # 编译后的可执行文件


# ============================================
# 核心评测函数
# ============================================

def set_limits(time_limit: float, memory_limit: int) -> None:
    """
    设置进程资源限制
    """
    # CPU 时间限制（加一点缓冲）
    resource.setrlimit(resource.RLIMIT_CPU, (time_limit + 0.5, time_limit + 0.5))
    # 内存限制（地址空间）
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
    # 文件大小限制（防止输出过大）
    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))  # 10MB


def compile_code() -> Tuple[bool, str]:
    """
    编译 C++ 代码
    返回: (是否成功, 错误信息)
    """
    # 删除旧的编译产物
    if EXEC_FILE.exists():
        EXEC_FILE.unlink()
    
    # 编译命令
    compile_cmd = [
        "g++",
        "-O2",           # 优化
        "-std=c++17",    # 使用 C++17
        "-Wall",         # 显示所有警告
        "-DONLINE_JUDGE", # 定义在线评测宏
        str(SOURCE_FILE),
        "-o",
        str(EXEC_FILE)
    ]
    
    try:
        print(f"🔨 编译中: {' '.join(compile_cmd)}")
        result = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=30  # 编译超时 30 秒
        )
        
        if result.returncode != 0:
            # 编译失败
            error_msg = result.stderr or result.stdout or "编译错误"
            return False, error_msg
        
        # 检查可执行文件是否生成
        if not EXEC_FILE.exists():
            return False, "可执行文件未生成"
        
        # 设置可执行权限
        EXEC_FILE.chmod(0o755)
        
        return True, None
        
    except subprocess.TimeoutExpired:
        return False, "编译超时（>30秒）"
    except Exception as e:
        return False, f"编译异常: {str(e)}"


def run_testcase(input_file: Path, output_file: Path) -> Tuple[str, str, float, int]:
    """
    运行单个测试用例
    返回: (状态, 实际输出, 耗时, 内存使用)
    """
    # 读取输入
    try:
        with open(input_file, 'r') as f:
            input_data = f.read()
    except Exception as e:
        return "RE", f"读取输入文件失败: {e}", 0, 0
    
    # 检查可执行文件
    if not EXEC_FILE.exists():
        return "RE", "可执行文件不存在", 0, 0
    
    start_time = time.time()
    memory_usage = 0
    
    try:
        # 运行程序
        result = subprocess.run(
            [str(EXEC_FILE)],
            input=input_data,
            capture_output=True,
            text=True,
            preexec_fn=lambda: set_limits(TIME_LIMIT, MEMORY_LIMIT),
            timeout=TIME_LIMIT + 0.5  # 额外缓冲
        )
        
        elapsed = time.time() - start_time
        
        # 获取内存使用（Linux）
        try:
            import psutil
            # 注意：psutil 需要安装
        except ImportError:
            pass  # 如果没装 psutil，跳过内存统计
        
        # 检查是否超时（由 timeout 捕获）
        if elapsed >= TIME_LIMIT:
            return "TLE", "", elapsed, 0
        
        # 检查运行时错误（段错误、浮点异常等）
        if result.returncode != 0:
            # 检查是否是内存超限（通过退出码判断，但不够准确）
            return "RE", result.stderr or f"退出码: {result.returncode}", elapsed, 0
        
        # 读取期望输出
        try:
            with open(output_file, 'r') as f:
                expected = f.read().strip()
        except Exception as e:
            return "RE", f"读取期望输出失败: {e}", elapsed, 0
        
        # 获取实际输出
        actual = result.stdout.strip()
        
        # 比较输出
        if actual == expected:
            return "AC", actual, elapsed, memory_usage
        else:
            return "WA", actual, elapsed, memory_usage
        
    except subprocess.TimeoutExpired:
        return "TLE", "", TIME_LIMIT, 0
    except MemoryError:
        return "MLE", "", 0, MEMORY_LIMIT
    except Exception as e:
        return "RE", str(e), 0, 0


def get_testcases() -> list:
    """
    获取所有测试用例
    返回: [(输入文件路径, 输出文件路径), ...]
    """
    if not TESTCASE_DIR.exists():
        print(f"⚠️ 测试用例目录不存在: {TESTCASE_DIR}")
        return []
    
    in_files = sorted(TESTCASE_DIR.glob("*.in"))
    testcases = []
    
    for in_file in in_files:
        out_file = in_file.with_suffix(".out")
        if not out_file.exists():
            print(f"⚠️ 缺少输出文件: {out_file}")
            continue
        testcases.append((in_file, out_file))
    
    return testcases


def main() -> int:
    """
    主函数
    返回退出码: 0=成功, 1=失败
    """
    print("=" * 60)
    print("📝 A+B Problem 评测系统")
    print("=" * 60)
    
    # ============================================
    # 1. 编译
    # ============================================
    print("\n[1/3] 编译代码...")
    compile_ok, compile_error = compile_code()
    
    if not compile_ok:
        print(f"❌ 编译失败 (CE)")
        print(f"错误信息:\n{compile_error}")
        
        # 输出 JSON 结果
        result = {
            "final_status": "CE",
            "details": [],
            "total": 0,
            "passed": 0,
            "compile_error": compile_error
        }
        print("\n" + "=" * 60)
        print("RESULT_JSON:" + json.dumps(result))
        return 0
    
    print("✅ 编译成功")
    
    # ============================================
    # 2. 获取测试用例
    # ============================================
    print("\n[2/3] 加载测试用例...")
    testcases = get_testcases()
    
    if not testcases:
        print("❌ 没有找到测试用例")
        result = {
            "final_status": "WA",
            "details": [],
            "total": 0,
            "passed": 0,
            "error": "No testcases found"
        }
        print("\n" + "=" * 60)
        print("RESULT_JSON:" + json.dumps(result))
        return 0
    
    print(f"✅ 找到 {len(testcases)} 个测试用例")
    
    # ============================================
    # 3. 运行所有测试用例
    # ============================================
    print("\n[3/3] 运行测试用例...")
    print("-" * 60)
    
    results = []
    passed_count = 0
    total_time = 0
    
    for i, (in_file, out_file) in enumerate(testcases, 1):
        print(f"测试用例 #{i}: {in_file.name} → {out_file.name}")
        
        status, output, elapsed, memory = run_testcase(in_file, out_file)
        total_time += elapsed
        
        results.append({
            "testcase": in_file.name,
            "status": status,
            "time": round(elapsed, 3),
            "memory": memory,
            "output": output[:200]  # 只保留前200字符
        })
        
        # 显示结果
        status_emoji = {
            "AC": "✅", "WA": "❌", "TLE": "⏰",
            "RE": "💥", "MLE": "💾", "CE": "🔧"
        }.get(status, "❓")
        
        print(f"  {status_emoji} {status}  (用时: {elapsed:.3f}s)")
        
        if status == "AC":
            passed_count += 1
        elif status == "WA":
            # 显示期望 vs 实际（简短）
            try:
                with open(out_file, 'r') as f:
                    expected = f.read().strip()[:50]
                print(f"  期望: {expected}")
                print(f"  实际: {output[:50]}")
            except:
                pass
    
    # ============================================
    # 4. 输出最终结果
    # ============================================
    print("-" * 60)
    print(f"\n📊 评测完成!")
    print(f"  通过: {passed_count}/{len(testcases)}")
    print(f"  总用时: {total_time:.3f}s")
    
    # 判断最终状态
    if passed_count == len(testcases):
        final_status = "AC"
        print(f"  最终结果: ✅ AC (答案正确)")
    else:
        # 找到第一个非 AC 的状态
        for r in results:
            if r["status"] != "AC":
                final_status = r["status"]
                break
        else:
            final_status = "WA"
        print(f"  最终结果: ❌ {final_status}")
    
    # 输出 JSON 格式结果（供 GitHub Actions 解析）
    result = {
        "final_status": final_status,
        "details": results,
        "total": len(testcases),
        "passed": passed_count,
        "total_time": round(total_time, 3)
    }
    
    print("\n" + "=" * 60)
    print("📤 输出 JSON 结果:")
    print(json.dumps(result, indent=2))
    print("=" * 60)
    
    # 特殊标记，方便 GitHub Actions 提取
    print("\nRESULT_JSON:" + json.dumps(result))
    
    return 0 if final_status == "AC" else 1


# ============================================
# 入口
# ============================================
if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️ 评测被中断")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 评测异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
