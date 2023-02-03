use core::fmt::Display;
use std::collections::HashMap;
use std::default;

use interval::Interval;
use lalrpop_util::lalrpop_mod;

lalrpop_mod!(pub parser);

pub mod extent_analysis;
pub mod source;
pub mod index_elim;
pub mod index_elim2;
pub mod index_free;
pub mod typechecker;

pub use self::source::*;
pub use self::index_free::*;

pub type DimSize = usize;
pub type Extent = Interval<i64>;
pub type Shape = im::Vector<Extent>;

pub type IndexName = String;
pub type ArrayName = String;

pub type ArrayEnvironment = HashMap<ArrayName, Shape>;
pub type IndexEnvironment = HashMap<IndexName, Extent>;

pub type ExprRefId = usize;

#[derive(Copy,Clone,Debug)]
pub enum Operator { Add, Sub, Mul }

impl Display for Operator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Operator::Add => write!(f, "+"),
            Operator::Sub => write!(f, "-"),
            Operator::Mul => write!(f, "*"),
        }
    }
}

pub type DimIndex = usize;

// an dimension of an abstract (read: not materialized) array
#[derive(Clone,Debug,PartialEq,Eq,Hash)]
pub enum DimContent {
    // a dimension where array elements change along one specific dimension
    // of the array being indexed
    FilledDim { dim: DimIndex, extent: usize, stride: isize },

    // a dimension where array elements do not change
    EmptyDim { extent: usize }
}

impl DimContent {
    pub fn extent(&self) -> usize {
        match self {
            DimContent::FilledDim { dim: _, extent, stride: _ } => *extent,
            DimContent::EmptyDim { extent } => *extent
        }
    }
}

impl Display for DimContent {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DimContent::FilledDim { dim, extent, stride } => {
                write!(f, "{{{}:{}::{}}}", dim, extent, stride)
            },

            DimContent::EmptyDim { extent } => {
                write!(f, "{{{}}}", extent)
            },
        }
    }
}

pub struct OffsetMap<T> { map: Vec<T> }

type BaseOffsetMap = OffsetMap<isize>;

impl<T: Default+Display+Clone> OffsetMap<T> {
    pub fn new(num_dims: usize) -> Self {
        let map = vec![T::default(); num_dims];
        OffsetMap { map }
    }

    pub fn set_offset(&mut self, dim: DimIndex, offset: T) {
        self.map[dim] = offset
    }

    pub fn get_offset(&self, dim: usize) -> &T {
        &self.map[dim]
    }

    pub fn num_dims(&self) -> usize {
        self.map.len()
    }
}

impl<T: Display> Display for OffsetMap<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}",
            self.map.iter()
                .map(|x| x.to_string())
                .collect::<Vec<String>>()
                .join(", ")
        )
    }
}

pub struct ArrayTransform<T: Display> {
    pub array: ArrayName,
    pub offset_map: OffsetMap<T>,
    pub dims: Vec<DimContent>,
}

pub type BaseArrayTransform = ArrayTransform<isize>;

impl<T: Display> Display for ArrayTransform<T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}[{}]<{}>",
            self.array,
            self.offset_map,
            self.dims.iter()
                .map(|dim| dim.to_string())
                .collect::<Vec<String>>()
                .join(", ")
        )
    }
}
