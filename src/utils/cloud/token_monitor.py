#!/usr/bin/env python3
"""Token operation monitoring and logging for race condition detection"""

import threading
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque


@dataclass
class TokenOperation:
    """Represents a token operation for monitoring"""
    operation_type: str  # 'refresh', 'read', 'write', 'validate'
    service: str  # 'sharepoint' or 'google_drive'
    thread_id: int
    timestamp: float
    duration: Optional[float] = None
    success: Optional[bool] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TokenOperationMonitor:
    """Thread-safe monitor for token operations to detect race conditions"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.logger = logging.getLogger(__name__)
        
        # Thread-safe storage
        self._lock = threading.RLock()
        self._operations: deque = deque(maxlen=max_history)
        self._active_operations: Dict[str, TokenOperation] = {}
        self._operation_counts: Dict[str, int] = defaultdict(int)
        self._race_condition_alerts: List[Dict[str, Any]] = []
        
        # Performance tracking
        self._refresh_times = defaultdict(list)
        self._concurrent_operation_count = defaultdict(int)
        
    def start_operation(self, operation_type: str, service: str, metadata: Dict[str, Any] = None) -> str:
        """Start tracking a token operation"""
        operation_id = f"{service}_{operation_type}_{threading.current_thread().ident}_{time.time()}"
        
        operation = TokenOperation(
            operation_type=operation_type,
            service=service,
            thread_id=threading.current_thread().ident,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        with self._lock:
            self._active_operations[operation_id] = operation
            self._operation_counts[f"{service}_{operation_type}"] += 1
            self._concurrent_operation_count[f"{service}_{operation_type}"] += 1
            
            # Check for potential race conditions
            self._check_concurrent_operations(operation_type, service)
            
        self.logger.debug(f"Started {operation_type} operation for {service} (ID: {operation_id})")
        return operation_id
    
    def end_operation(self, operation_id: str, success: bool = True, error: str = None) -> None:
        """End tracking a token operation"""
        with self._lock:
            if operation_id not in self._active_operations:
                self.logger.warning(f"Attempted to end unknown operation: {operation_id}")
                return
            
            operation = self._active_operations.pop(operation_id)
            operation.duration = time.time() - operation.timestamp
            operation.success = success
            operation.error = error
            
            # Record completed operation
            self._operations.append(operation)
            
            # Update concurrent operation count
            op_key = f"{operation.service}_{operation.operation_type}"
            self._concurrent_operation_count[op_key] = max(0, self._concurrent_operation_count[op_key] - 1)
            
            # Track refresh performance
            if operation.operation_type == 'refresh':
                self._refresh_times[operation.service].append(operation.duration)
                # Keep only last 50 refresh times
                if len(self._refresh_times[operation.service]) > 50:
                    self._refresh_times[operation.service] = self._refresh_times[operation.service][-50:]
        
        status = "succeeded" if success else "failed"
        self.logger.info(f"Completed {operation.operation_type} operation for {operation.service} "
                        f"in {operation.duration:.3f}s ({status})")
    
    def _check_concurrent_operations(self, operation_type: str, service: str) -> None:
        """Check for potential race conditions with concurrent operations"""
        current_time = time.time()
        
        # Count similar operations in progress
        similar_ops = [
            op for op in self._active_operations.values()
            if op.service == service and op.operation_type == operation_type
            and current_time - op.timestamp < 60  # Within last minute
        ]
        
        if len(similar_ops) > 1:
            # Multiple operations of same type for same service - potential race condition
            alert = {
                'timestamp': current_time,
                'service': service,
                'operation_type': operation_type,
                'concurrent_count': len(similar_ops),
                'thread_ids': [op.thread_id for op in similar_ops],
                'message': f"Detected {len(similar_ops)} concurrent {operation_type} operations for {service}"
            }
            self._race_condition_alerts.append(alert)
            self.logger.warning(f"RACE CONDITION ALERT: {alert['message']}")
            
            # Keep only last 100 alerts
            if len(self._race_condition_alerts) > 100:
                self._race_condition_alerts = self._race_condition_alerts[-100:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive statistics about token operations"""
        with self._lock:
            current_time = time.time()
            
            # Calculate operation statistics
            total_operations = len(self._operations)
            successful_operations = sum(1 for op in self._operations if op.success)
            failed_operations = total_operations - successful_operations
            
            # Recent operations (last 5 minutes)
            recent_ops = [op for op in self._operations if current_time - op.timestamp < 300]
            
            # Average refresh times
            avg_refresh_times = {}
            for service, times in self._refresh_times.items():
                if times:
                    avg_refresh_times[service] = sum(times) / len(times)
            
            stats = {
                'total_operations': total_operations,
                'successful_operations': successful_operations,
                'failed_operations': failed_operations,
                'success_rate': successful_operations / total_operations if total_operations > 0 else 0,
                'recent_operations_count': len(recent_ops),
                'active_operations_count': len(self._active_operations),
                'concurrent_operations': dict(self._concurrent_operation_count),
                'operation_counts': dict(self._operation_counts),
                'average_refresh_times': avg_refresh_times,
                'race_condition_alerts': len(self._race_condition_alerts),
                'last_alert': self._race_condition_alerts[-1] if self._race_condition_alerts else None
            }
            
            return stats
    
    def get_race_condition_alerts(self) -> List[Dict[str, Any]]:
        """Get all race condition alerts"""
        with self._lock:
            return self._race_condition_alerts.copy()
    
    def get_recent_operations(self, limit: int = 50) -> List[TokenOperation]:
        """Get recent operations"""
        with self._lock:
            return list(self._operations)[-limit:]
    
    def clear_history(self) -> None:
        """Clear operation history (useful for testing)"""
        with self._lock:
            self._operations.clear()
            self._race_condition_alerts.clear()
            self._refresh_times.clear()
            self._operation_counts.clear()
            self.logger.info("Cleared token operation history")
    
    def log_performance_summary(self) -> None:
        """Log a summary of token operation performance"""
        stats = self.get_statistics()
        
        self.logger.info("=== Token Operation Performance Summary ===")
        self.logger.info(f"Total operations: {stats['total_operations']}")
        self.logger.info(f"Success rate: {stats['success_rate']:.2%}")
        self.logger.info(f"Active operations: {stats['active_operations_count']}")
        self.logger.info(f"Race condition alerts: {stats['race_condition_alerts']}")
        
        if stats['average_refresh_times']:
            self.logger.info("Average refresh times:")
            for service, avg_time in stats['average_refresh_times'].items():
                self.logger.info(f"  {service}: {avg_time:.3f}s")
        
        if stats['concurrent_operations']:
            self.logger.info("Current concurrent operations:")
            for op_type, count in stats['concurrent_operations'].items():
                if count > 0:
                    self.logger.info(f"  {op_type}: {count}")


# Global monitor instance
_global_monitor = None
_monitor_lock = threading.RLock()


def get_token_monitor() -> TokenOperationMonitor:
    """Get the global token operation monitor instance (thread-safe)"""
    global _global_monitor
    with _monitor_lock:
        if _global_monitor is None:
            _global_monitor = TokenOperationMonitor()
        return _global_monitor


def monitor_token_operation(operation_type: str, service: str, metadata: Dict[str, Any] = None):
    """Decorator to monitor token operations"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = get_token_monitor()
            operation_id = monitor.start_operation(operation_type, service, metadata)
            
            try:
                result = func(*args, **kwargs)
                monitor.end_operation(operation_id, success=True)
                return result
            except Exception as e:
                monitor.end_operation(operation_id, success=False, error=str(e))
                raise
        
        return wrapper
    return decorator