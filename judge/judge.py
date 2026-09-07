#!/usr/bin/env python3
"""
A+B Problem 评测脚本
支持: AC, WA, TLE, RE, MLE, CE
包含完整的内存监控
"""

import subprocess
import resource
import time
import os
import sys
import json
import shutil
import threading
import psutil
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

# ============================================
# 配置
# ============================================
TIME_LIMIT = 1.0  # 秒
MEMORY_LIMIT_MB = 512  # MB
MEMORY_LIMIT_BYTES = MEMORY_LIMIT_MB * 1024 * 1024  # 512MB（字节）

# 路径配置
BASE_DIR = Path(__file__).parent
TESTCASE_DIR = BASE_DIR / "testcases"
SOURCE_FILE = BASE_DIR / "solution.cpp"
EXEC_FILE = Path("/tmp/solution")  # 编译后的可执行文件


# ============================================
# 内存监控类
# ============================================
class MemoryMonitor:
    """
    实时监控子进程内存使用
    """
    def __init__(self, pid: int, limit_mb: int):
        self.pid = pid
        self.limit_mb = limit_mb
        self.max_memory_mb = 0
        self.is_exceeded = False
        self._stop_monitoring = False
        self._thread = None
        
    def start(self):
        """启动监控线程"""
        self._stop_monitoring = False
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
        
    def stop(self) -> Tuple[int, bool]:
        """
        停止监控
        返回: (最大内存MB, 是否超限)
        """
        self._stop_monitoring = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        return self.max_memory_mb, self.is_exceeded
    
    def _monitor(self):
        """监控循环"""
        try:
            process = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            return
        
        while not self._stop_monitoring:
            try:
                # 获取进程及其子进程的内存使用
                memory_mb = 0
                try:
                    # 获取主进程内存
                    mem_info = process.memory_info()
                    memory_mb = mem_info.rss / (1024 * 1024)
                    
                    # 获取子进程内存
                    for child in process.children(recursive=True):
                        try:
                            child_mem = child.memory_info().rss / (1024 * 1024)
                            memory_mb += child_mem
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # 更新最大内存
                if memory_mb > self.max_memory_mb:
                    self.max_memory_mb = memory_mb
                
                # 检查是否超限
                if memory_mb > self.limit_mb:
                    self.is_exceeded = True
                    # 尝试杀死进程
                    try:
                        process.terminate()
                    except:
                        pass
                    break
                    
            except Exception:
                pass
            
            time.sleep(0.01)  # 10ms 采样间隔


# ============================================
# 资源限制函数
# ============================================
def set_limits(time_limit: float, memory_limit_bytes: int) -> None:
    """
    设置进程资源限制（使用 resource 模块）
    注意：这会在子进程启动时调用
    """
    # CPU 时间限制
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (time_limit + 0.5, time_limit + 0.5))
    except ValueError:
        pass  # 某些系统可能不支持
    
    # 内存限制（地址空间）
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
    except ValueError:
        pass
    
    # 文件大小限制（防止输出过大）
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))  # 10MB
    except ValueError:
        pass


def get_memory_usage_mb(pid: int) -> float:
    """
    获取进程内存使用（MB）
    """
    try:
        process = psutil.Process(pid)
        total_memory = 0
        
        # 主进程
        try:
            total_memory += process.memory_info().rss
        except:
            pass
        
        # 子进程
        try:
            for child in process.children(recursive=True):
                try:
                    total_memory += child.memory_info().rss
                except:
                    pass
        except:
            pass
        
        return total_memory / (1024 * 1024)
    except:
        return 0


# ============================================
# 编译函数
# ============================================
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
        "-O2",
        "-std=c++17",
        "-Wall",
        "-DONLINE_JUDGE",
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
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "编译错误"
            return False, error_msg
        
        if not EXEC_FILE.exists():
            return False, "可执行文件未生成"
        
        EXEC_FILE.chmod(0o755)
        return True, None
        
    except subprocess.TimeoutExpired:
        return False, "编译超时（>30秒）"
    except Exception as e:
        return False, f"编译异常: {str(e)}"


# ============================================
# 运行测试用例（含内存监控）
# ============================================
def run_testcase(input_file: Path, output_file: Path) -> Tuple[str, str, float, float]:
    """
    运行单个测试用例
    返回: (状态, 实际输出, 耗时, 内存使用MB)
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
    max_memory_mb = 0
    memory_exceeded = False
    
    # 使用 subprocess.Popen 以便获取 PID
    process = None
    monitor = None
    
    try:
        # 启动子进程
        process = subprocess.Popen(
            [str(EXEC_FILE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: set_limits(TIME_LIMIT, MEMORY_LIMIT_BYTES) if os.name == 'posix' else None
        )
        
        # 启动内存监控
        monitor = MemoryMonitor(process.pid, MEMORY_LIMIT_MB)
        monitor.start()
        
        # 等待进程结束（带超时）
        try:
            stdout, stderr = process.communicate(input=input_data, timeout=TIME_LIMIT + 0.5)
            elapsed = time.time() - start_time
        except subprocess.TimeoutExpired:
            # 超时，杀死进程
            process.kill()
            process.communicate()
            elapsed = time.time() - start_time
            return "TLE", "", elapsed, 0
        
        # 停止内存监控
        max_memory_mb, memory_exceeded = monitor.stop()
        
        # 检查内存是否超限
        if memory_exceeded or max_memory_mb > MEMORY_LIMIT_MB:
            return "MLE", "", elapsed, max_memory_mb
        
        # 检查是否超时（通过 elapsed 判断）
        if elapsed >= TIME_LIMIT:
            return "TLE", "", elapsed, max_memory_mb
        
        # 检查运行时错误
        if process.returncode != 0:
            error_msg = stderr or f"退出码: {process.returncode}"
            return "RE", error_msg, elapsed, max_memory_mb
        
        # 读取期望输出
        try:
            with open(output_file, 'r') as f:
                expected = f.read().strip()
        except Exception as e:
            return "RE", f"读取期望输出失败: {e}", elapsed, max_memory_mb
        
        # 获取实际输出
        actual = stdout.strip()
        
        # 比较输出
        if actual == expected:
            return "AC", actual, elapsed, max_memory_mb
        else:
            return "WA", actual, elapsed, max_memory_mb
        
    except subprocess.TimeoutExpired:
        if process:
            try:
                process.kill()
                process.communicate()
            except:
                pass
        return "TLE", "", TIME_LIMIT, 0
    except MemoryError:
        return "MLE", "", 0, MEMORY_LIMIT_MB
    except Exception as e:
        if monitor:
            try:
                monitor.stop()
            except:
                pass
        return "RE", str(e), 0, 0
    finally:
        # 清理
        if process and process.poll() is None:
            try:
                process.kill()
                process.communicate()
            except:
                pass


# ============================================
# 获取测试用例
# ============================================
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


# ============================================
# 检查测试用例格式
# ============================================
def check_testcases():
    """检查测试用例是否正确"""
    testcases = get_testcases()
    if not testcases:
        return False
    
    print(f"\n📋 找到 {len(testcases)} 个测试用例:")
    for in_file, out_file in testcases:
        # 读取输入和输出的第一行预览
        try:
            with open(in_file, 'r') as f:
                in_preview = f.readline().strip()[:50]
            with open(out_file, 'r') as f:
                out_preview = f.readline().strip()[:50]
            print(f"  {in_file.name} → {out_file.name}")
            print(f"    输入: {in_preview}")
            print(f"    输出: {out_preview}")
        except:
            print(f"  {in_file.name} → {out_file.name} (无法读取)")
    
    return True


# ============================================
# 主函数
# ============================================
def main() -> int:
    """
    主函数
    返回退出码: 0=成功, 1=失败
    """
    print("=" * 60)
    print("📝 A+B Problem 评测系统 (含内存监控)")
    print("=" * 60)
    print(f"⏰ 时间限制: {TIME_LIMIT}s")
    print(f"💾 内存限制: {MEMORY_LIMIT_MB}MB")
    
    # ============================================
    # 1. 检查测试用例
    # ============================================
    print("\n[1/4] 检查测试用例...")
    if not check_testcases():
        result = {
            "final_status": "WA",
            "details": [],
            "total": 0,
            "passed": 0,
            "error": "No valid testcases found"
        }
        print("\n" + "=" * 60)
        print("RESULT_JSON:" + json.dumps(result))
        return 1
    
    # ============================================
    # 2. 编译
    # ============================================
    print("\n[2/4] 编译代码...")
    compile_ok, compile_error = compile_code()
    
    if not compile_ok:
        print(f"❌ 编译失败 (CE)")
        print(f"错误信息:\n{compile_error}")
        
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
    # 3. 获取测试用例
    # ============================================
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
    
    # ============================================
    # 4. 运行所有测试用例
    # ============================================
    print(f"\n[3/4] 运行测试用例 (共 {len(testcases)} 个)...")
    print("-" * 60)
    
    results = []
    passed_count = 0
    total_time = 0
    max_memory_overall = 0
    
    for i, (in_file, out_file) in enumerate(testcases, 1):
        print(f"测试用例 #{i}: {in_file.name}")
        
        status, output, elapsed, memory_mb = run_testcase(in_file, out_file)
        total_time += elapsed
        if memory_mb > max_memory_overall:
            max_memory_overall = memory_mb
        
        results.append({
            "testcase": in_file.name,
            "status": status,
            "time": round(elapsed, 3),
            "memory": round(memory_mb, 2),
            "output": output[:200] if output else ""
        })
        
        # 显示结果
        status_emoji = {
            "AC": "✅", "WA": "❌", "TLE": "⏰",
            "RE": "💥", "MLE": "💾", "CE": "🔧"
        }.get(status, "❓")
        
        memory_str = f"内存: {memory_mb:.1f}MB" if memory_mb > 0 else "内存: N/A"
        print(f"  {status_emoji} {status}  (用时: {elapsed:.3f}s, {memory_str})")
        
        if status == "AC":
            passed_count += 1
        elif status == "WA":
            try:
                with open(out_file, 'r') as f:
                    expected = f.read().strip()[:80]
                print(f"    期望: {expected}")
                print(f"    实际: {output[:80] if output else '(空)'}")
            except:
                pass
        elif status == "MLE":
            print(f"    💾 内存超限: {memory_mb:.1f}MB > {MEMORY_LIMIT_MB}MB")
    
    # ============================================
    # 5. 输出最终结果
    # ============================================
    print("-" * 60)
    print(f"\n[4/4] 评测完成!")
    print(f"  ✅ 通过: {passed_count}/{len(testcases)}")
    print(f"  ⏰ 总用时: {total_time:.3f}s")
    print(f"  💾 最大内存: {max_memory_overall:.1f}MB")
    
    # 判断最终状态
    if passed_count == len(testcases):
        final_status = "AC"
        print(f"  🎉 最终结果: AC (答案正确)")
    else:
        # 找到第一个非 AC 的状态（按优先级：MLE > TLE > RE > WA > CE）
        for status in ["MLE", "TLE", "RE", "WA", "CE"]:
            for r in results:
                if r["status"] == status:
                    final_status = status
                    break
            if final_status:
                break
        else:
            final_status = "WA"
        print(f"  ❌ 最终结果: {final_status}")
    
    # 输出 JSON 格式结果
    result = {
        "final_status": final_status,
        "details": results,
        "total": len(testcases),
        "passed": passed_count,
        "total_time": round(total_time, 3),
        "max_memory": round(max_memory_overall, 2)
    }
    
    print("\n" + "=" * 60)
    print("📤 JSON 结果:")
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
