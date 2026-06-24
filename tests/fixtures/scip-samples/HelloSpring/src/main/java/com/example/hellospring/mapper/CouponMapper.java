package com.example.hellospring.mapper;

import java.math.BigDecimal;
import java.util.List;

public interface CouponMapper {

    List<BigDecimal> selectByUser(long userId);
}
